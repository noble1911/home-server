"""Host agent — runs on the Mac Mini host (not in Docker).

Butler API (in Docker) can only see the OrbStack Linux VM: its /proc says
nothing about the Mac's real CPU/RAM, the native apps (Jellyfin, Ollama,
OrbStack itself), or drives that aren't bind-mounted into the container. This
tiny aiohttp service fills that gap from the host side:

    GET  /health            liveness + what's enabled
    GET  /metrics           host CPU/RAM/swap/load, top processes, per-container stats
    GET  /storage           every configured drive: usage + category sizes (cached du)
    GET  /history           last hour of host cpu/mem/swap + container totals (for charts)
    GET  /trash             items + bytes in the inbox Trash
    POST /trash/empty       delete the Trash's contents (and nothing else)
    POST /move              start a move job (allow-listed source -> destination)
    GET  /jobs              recent move jobs with progress
    GET  /jobs/{id}         one job

Everything except /health requires the X-Agent-Token header to match
HOST_AGENT_TOKEN (constant-time compare). The sampler runs in the background so
requests never block on `docker stats` or `du`.

Configuration (environment):
    HOST_AGENT_TOKEN   shared secret (required for /metrics, /storage, /move, /jobs)
    HOST_AGENT_PORT    default 7101
    HOST_AGENT_HOST    default 0.0.0.0 (must be reachable from the Docker VM)
    HOST_AGENT_DRIVES  JSON list overriding DEFAULT_DRIVES
    HOST_AGENT_MOVE_SOURCES / HOST_AGENT_MOVE_DESTINATIONS  colon-separated
                       allow-lists overriding the defaults below

Setup: see scripts/16-host-agent.sh (venv + launchd plist).
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import psutil
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("host-agent")

HOME = Path.home()
PORT = int(os.environ.get("HOST_AGENT_PORT", "7101"))
HOST = os.environ.get("HOST_AGENT_HOST", "0.0.0.0")
TOKEN = os.environ.get("HOST_AGENT_TOKEN", "").strip()

METRICS_INTERVAL = 5          # seconds between CPU/RAM samples
DOCKER_STATS_INTERVAL = 20    # `docker stats` is slow (~2 s); sample less often
DU_INTERVAL = 15 * 60         # category sizes: du over TBs is expensive
TOP_N = 8

# Native processes worth naming on the dashboard (substring match on exe/name).
KNOWN_APPS = {
    "Jellyfin": ("jellyfin",),
    "Ollama": ("ollama",),
    "OrbStack (Docker VM)": ("orbstack",),
    "WirePod": ("wire-pod", "wirepod"),
    "Home Agent": ("host-agent",),
}

# Drives to report. `categories` are subfolders whose size is worth showing.
DEFAULT_DRIVES: list[dict[str, Any]] = [
    {
        "name": "Mac SSD",
        "path": "/",
        "role": "system",
        "categories": {
            "Docker (OrbStack)": str(HOME / "Library/Group Containers/HUAQ24HBR6.dev.orbstack"),
            "Ollama models": str(HOME / ".ollama"),
            "Jellyfin data": str(HOME / "Library/Application Support/jellyfin"),
        },
    },
    {
        "name": "HomeServer",
        "path": "/Volumes/HomeServer",
        "role": "downloads",
        "categories": {
            "Anime": "/Volumes/HomeServer/Media/Anime",
            "Downloads": "/Volumes/HomeServer/Downloads",
            "Books": "/Volumes/HomeServer/Books",
            "Photos": "/Volumes/HomeServer/Photos",
            "Documents": "/Volumes/HomeServer/Documents",
            "Config": "/Volumes/HomeServer/Config",
            "Backups": "/Volumes/HomeServer/Backups",
            "Movies": "/Volumes/HomeServer/Media/Movies",
            "TV Shows": "/Volumes/HomeServer/Media/TV",
        },
    },
    {
        "name": "HomeServer2",
        "path": "/Volumes/HomeServer2",
        "role": "library",
        "categories": {
            "Movies": "/Volumes/HomeServer2/Media/Movies",
            "TV Shows": "/Volumes/HomeServer2/Media/TV",
            "Anime": "/Volumes/HomeServer2/Media/Anime",
        },
    },
]

DEFAULT_MOVE_SOURCES = ["/Volumes/HomeServer/Downloads/Complete"]
# The inbox's holding pen. /trash/empty deletes its *contents* and nothing else.
TRASH_DIR = os.environ.get("HOST_AGENT_TRASH_DIR", "/Volumes/HomeServer/Downloads/Trash")
HISTORY_SECONDS = 60 * 60     # keep an hour of samples for the charts
DEFAULT_MOVE_DESTINATIONS = [
    "/Volumes/HomeServer2/Media",
    "/Volumes/HomeServer/Media",
    "/Volumes/HomeServer/Downloads/Trash",   # holding pen; never auto-emptied
]


def _load_drives() -> list[dict[str, Any]]:
    raw = os.environ.get("HOST_AGENT_DRIVES")
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("HOST_AGENT_DRIVES is not valid JSON; using defaults")
    return DEFAULT_DRIVES


DRIVES = _load_drives()
MOVE_SOURCES = [p for p in os.environ.get("HOST_AGENT_MOVE_SOURCES", ":".join(DEFAULT_MOVE_SOURCES)).split(":") if p]
MOVE_DESTINATIONS = [p for p in os.environ.get("HOST_AGENT_MOVE_DESTINATIONS", ":".join(DEFAULT_MOVE_DESTINATIONS)).split(":") if p]

DOCKER_BIN = next((p for p in ("/usr/local/bin/docker", "/opt/homebrew/bin/docker") if Path(p).exists()), "docker")


# ── macOS privacy (TCC) ──────────────────────────────────────────────
#
# A launchd-spawned Python has no "Files and Folders → Removable Volumes" /
# Full Disk Access grant by default. The first os.listdir() on an external
# drive then BLOCKS on a consent prompt nobody may ever see. Probe each drive
# with a timeout so we can say so instead of silently hanging du and moves.

DISK_ACCESS: dict[str, bool | None] = {}   # drive path -> True/False/None(unknown)


def _grant_path() -> str:
    """What to add in System Settings → Privacy & Security → Full Disk Access.

    Homebrew's bin/python3.x is a stub that execs Python.app inside the
    framework; macOS attributes the permission to that bundle, and the file
    picker only lets you select the bundle (the stub shows greyed out).
    """
    try:
        exe = psutil.Process().exe()
    except Exception:
        exe = os.path.realpath(sys.executable)
    parts = exe.split("/")
    for i, part in enumerate(parts):
        if part.endswith(".app"):
            return "/".join(parts[: i + 1])
    return exe


PYTHON_BIN = _grant_path()


def _probe_disk_access() -> None:
    for d in DRIVES:
        path = d["path"]
        if not os.path.isdir(path):
            DISK_ACCESS[path] = None
            continue
        probe = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tcc-probe")
        fut = probe.submit(os.listdir, path)
        try:
            fut.result(timeout=5)
            DISK_ACCESS[path] = True
        except FutureTimeout:
            DISK_ACCESS[path] = False
            logger.error(
                "No permission to read %s (macOS privacy). Grant Full Disk Access to %s in "
                "System Settings → Privacy & Security, then restart the agent.", path, PYTHON_BIN,
            )
        except Exception as e:
            DISK_ACCESS[path] = False
            logger.error("Cannot read %s: %s", path, e)
        finally:
            probe.shutdown(wait=False, cancel_futures=True)


def _disk_ok(path: str) -> bool:
    """True unless a drive containing `path` is known to be blocked."""
    for drive, ok in DISK_ACCESS.items():
        if ok is False and (path == drive or path.startswith(drive.rstrip("/") + "/")):
            return False
    return True


# ── Auth ─────────────────────────────────────────────────────────────


def _authorized(request: web.Request) -> bool:
    if not TOKEN:
        return False
    return hmac.compare_digest(request.headers.get("X-Agent-Token", ""), TOKEN)


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if request.path != "/health" and not _authorized(request):
        logger.warning("Rejected %s %s from %s", request.method, request.path, request.remote)
        raise web.HTTPUnauthorized(reason="missing or invalid X-Agent-Token")
    return await handler(request)


# ── Sampler (background) ─────────────────────────────────────────────


class Sampler:
    """Keeps the latest host snapshot in memory; refreshed on timers."""

    def __init__(self) -> None:
        self.metrics: dict[str, Any] = {}
        self.containers: list[dict[str, Any]] = []
        self.containers_at: float = 0.0
        self.storage: dict[str, Any] = {}
        self.category_sizes: dict[str, dict[str, int | None]] = {}
        self.categories_at: float = 0.0
        self._procs: dict[int, psutil.Process] = {}
        # (t, cpu%, mem%, swap%) every METRICS_INTERVAL; (t, cpu%, mem bytes) per docker sample
        self.history: deque[tuple[float, float, float, float]] = deque(maxlen=HISTORY_SECONDS // METRICS_INTERVAL)
        self.docker_history: deque[tuple[float, float, int]] = deque(maxlen=HISTORY_SECONDS // DOCKER_STATS_INTERVAL)

    # -- metrics --

    def sample_metrics(self) -> None:
        cpu_percent = psutil.cpu_percent(interval=None)
        per_core = psutil.cpu_percent(interval=None, percpu=True)
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        load1, load5, load15 = os.getloadavg()
        disk_io = psutil.disk_io_counters()
        net_io = psutil.net_io_counters()

        procs = self._sample_processes()

        mem_pct = round((vm.total - vm.available) / vm.total * 100, 1) if vm.total else 0
        self.history.append((time.time(), round(cpu_percent, 1), mem_pct, round(swap.percent, 1)))

        self.metrics = {
            "sampledAt": time.time(),
            "uptimeSeconds": int(time.time() - psutil.boot_time()),
            "cpu": {
                "percent": round(cpu_percent, 1),
                "cores": psutil.cpu_count(logical=True) or 0,
                "perCore": [round(c, 1) for c in per_core],
                "load": [round(load1, 2), round(load5, 2), round(load15, 2)],
            },
            "memory": {
                "total": vm.total,
                "used": vm.total - vm.available,
                "available": vm.available,
                "percent": round((vm.total - vm.available) / vm.total * 100, 1) if vm.total else 0,
                "wired": getattr(vm, "wired", None),
                "active": getattr(vm, "active", None),
                "inactive": getattr(vm, "inactive", None),
            },
            "swap": {
                "total": swap.total,
                "used": swap.used,
                "percent": round(swap.percent, 1),
            },
            "diskIo": {"readBytes": disk_io.read_bytes, "writeBytes": disk_io.write_bytes} if disk_io else None,
            "netIo": {"bytesSent": net_io.bytes_sent, "bytesRecv": net_io.bytes_recv} if net_io else None,
            "processes": procs,
        }

    def _sample_processes(self) -> dict[str, Any]:
        """Top processes by CPU and RSS, plus the named native apps."""
        live: dict[int, psutil.Process] = {}
        rows: list[dict[str, Any]] = []
        for p in psutil.process_iter(["pid", "name", "exe", "memory_info"]):
            try:
                proc = self._procs.get(p.pid) or p
                live[p.pid] = proc
                cpu = proc.cpu_percent(interval=None)  # since last call — needs the cached object
                mem = p.info["memory_info"].rss if p.info.get("memory_info") else 0
                rows.append({
                    "pid": p.pid,
                    "name": p.info.get("name") or "?",
                    "exe": p.info.get("exe") or "",
                    "cpu": round(cpu, 1),
                    "rss": mem,
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        self._procs = live

        cores = psutil.cpu_count(logical=True) or 1
        apps: dict[str, dict[str, Any]] = {}
        for row in rows:
            hay = f"{row['exe']} {row['name']}".lower()
            for label, needles in KNOWN_APPS.items():
                if any(n in hay for n in needles):
                    a = apps.setdefault(label, {"name": label, "cpu": 0.0, "rss": 0, "pids": 0})
                    a["cpu"] += row["cpu"]
                    a["rss"] += row["rss"]
                    a["pids"] += 1
                    break
        for a in apps.values():
            # psutil per-process cpu is "of one core"; normalise to whole-machine %
            a["cpu"] = round(a["cpu"] / cores, 1)

        def _slim(r: dict[str, Any]) -> dict[str, Any]:
            return {"pid": r["pid"], "name": r["name"], "cpu": round(r["cpu"] / cores, 1), "rss": r["rss"]}

        return {
            "apps": sorted(apps.values(), key=lambda a: -a["rss"]),
            "topCpu": [_slim(r) for r in sorted(rows, key=lambda r: -r["cpu"])[:TOP_N] if r["cpu"] > 0],
            "topMemory": [_slim(r) for r in sorted(rows, key=lambda r: -r["rss"])[:TOP_N]],
        }

    # -- docker --

    def sample_containers(self) -> None:
        try:
            out = subprocess.run(
                [DOCKER_BIN, "stats", "--no-stream", "--format", "{{json .}}"],
                capture_output=True, text=True, timeout=25,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning("docker stats failed: %s", e)
            return
        rows = []
        for line in out.stdout.splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                "name": d.get("Name"),
                "cpu": _pct(d.get("CPUPerc")),
                "memory": _parse_size(d.get("MemUsage", "").split("/")[0]),
                "memoryPercent": _pct(d.get("MemPerc")),
            })
        self.containers = sorted(rows, key=lambda r: -(r["memory"] or 0))
        self.containers_at = time.time()
        self.docker_history.append((
            time.time(),
            round(sum(r["cpu"] or 0 for r in rows), 1),
            sum(r["memory"] or 0 for r in rows),
        ))

    # -- storage --

    def sample_storage(self) -> None:
        drives = []
        for d in DRIVES:
            path = d["path"]
            if not os.path.isdir(path):
                drives.append({"name": d["name"], "path": path, "role": d.get("role"), "mounted": False})
                continue
            st = os.statvfs(path)
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            used = total - free
            cats = []
            for label, cpath in (d.get("categories") or {}).items():
                exists = os.path.exists(cpath)
                link = os.path.islink(cpath)
                cats.append({
                    "label": label,
                    "path": cpath,
                    "exists": exists,
                    "linkedTo": os.path.realpath(cpath) if link else None,
                    "bytes": (self.category_sizes.get(d["name"]) or {}).get(label),
                })
            drives.append({
                "name": d["name"],
                "path": path,
                "role": d.get("role"),
                "mounted": True,
                "total": total,
                "used": used,
                "free": free,
                "percent": round(used / total * 100, 1) if total else 0,
                "categories": cats,
            })
        for dr in drives:
            dr["diskAccess"] = DISK_ACCESS.get(dr["path"])
        self.storage = {
            "sampledAt": time.time(),
            "categoriesAt": self.categories_at or None,
            "drives": drives,
            "diskAccess": all(v is not False for v in DISK_ACCESS.values()),
            "pythonBin": PYTHON_BIN,
        }

    def sample_categories(self) -> None:
        """du -sk each category (skipping symlinks — they'd double count)."""
        sizes: dict[str, dict[str, int | None]] = {}
        for d in DRIVES:
            per: dict[str, int | None] = {}
            for label, cpath in (d.get("categories") or {}).items():
                if not _disk_ok(cpath) or not os.path.exists(cpath) or os.path.islink(cpath):
                    per[label] = None
                    continue
                try:
                    out = subprocess.run(["du", "-sk", cpath], capture_output=True, text=True, timeout=1800)
                    per[label] = int(out.stdout.split()[0]) * 1024 if out.stdout.strip() else None
                except Exception as e:
                    logger.warning("du failed for %s: %s", cpath, e)
                    per[label] = None
            sizes[d["name"]] = per
        self.category_sizes = sizes
        self.categories_at = time.time()


def _pct(s: str | None) -> float | None:
    try:
        return float((s or "").strip().rstrip("%"))
    except ValueError:
        return None


def _parse_size(s: str) -> int | None:
    s = (s or "").strip()
    units = {"B": 1, "KIB": 1024, "MIB": 1024**2, "GIB": 1024**3, "TIB": 1024**4,
             "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4}
    num = "".join(c for c in s if (c.isdigit() or c == "."))
    unit = s[len(num):].strip().upper()
    try:
        return int(float(num) * units.get(unit, 1))
    except ValueError:
        return None


# ── Move jobs ────────────────────────────────────────────────────────


@dataclass
class MoveJob:
    id: str
    source: str
    destination: str
    status: str = "queued"          # queued | running | done | failed
    totalBytes: int = 0
    copiedBytes: int = 0
    files: int = 0
    filesDone: int = 0
    error: str | None = None
    startedAt: float = field(default_factory=time.time)
    finishedAt: float | None = None


JOBS: dict[str, MoveJob] = {}
MAX_JOBS = 50
# Moves get their own threads so a long `du` or a slow docker stats can never
# sit in front of them in the default executor's queue.
MOVE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="move")
DU_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="du")


def _within(path: str, roots: list[str]) -> bool:
    real = os.path.realpath(path)
    return any(real == os.path.realpath(r) or real.startswith(os.path.realpath(r) + os.sep) for r in roots)


def _same_device(a: str, b: str) -> bool:
    """True when both paths live on the same filesystem (rename is possible)."""
    try:
        # b may not exist yet — climb to the nearest existing ancestor
        while not os.path.exists(b):
            parent = os.path.dirname(b)
            if parent == b:
                return False
            b = parent
        return os.stat(a).st_dev == os.stat(b).st_dev
    except OSError:
        return False


def _tree_size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _tree_files(path: str) -> int:
    if os.path.isfile(path):
        return 1
    return sum(len(files) for _r, _d, files in os.walk(path))


def _run_move(job: MoveJob) -> None:
    """Copy file-by-file (progress), verify sizes, then delete the source."""
    src, dst = job.source, job.destination
    job.status = "running"
    logger.info("Move job %s started: %s", job.id, src)
    try:
        # Same volume? Then a rename is atomic and instant — no copying TBs
        # around just to change a path. Only fall back to copy+verify+delete
        # when the destination is on another device.
        if _same_device(src, os.path.dirname(dst)):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst):
                # Leftover from an interrupted earlier copy: park it, don't merge
                dst_old = f"{dst}.partial-{int(time.time())}"
                os.rename(dst, dst_old)
                logger.warning("Move job %s: destination existed, parked as %s", job.id, dst_old)
            job.totalBytes = _tree_size(src)
            job.files = _tree_files(src)
            os.rename(src, dst)
            job.copiedBytes = job.totalBytes
            job.filesDone = job.files
            job.status = "done"
            logger.info("Move job %s done (rename, same volume)", job.id)
            return

        if os.path.isfile(src):
            pairs = [(src, dst)]
        else:
            pairs = []
            for root, _dirs, files in os.walk(src):
                for f in files:
                    if f == ".DS_Store":
                        continue
                    s = os.path.join(root, f)
                    pairs.append((s, os.path.join(dst, os.path.relpath(s, src))))
        job.files = len(pairs)
        job.totalBytes = sum(os.path.getsize(s) for s, _ in pairs)
        logger.info("Move job %s: %d files, %d bytes", job.id, job.files, job.totalBytes)

        for s, d in pairs:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if os.path.exists(d) and os.path.getsize(d) == os.path.getsize(s):
                job.copiedBytes += os.path.getsize(s)
                job.filesDone += 1
                continue
            with open(s, "rb") as fi, open(d, "wb") as fo:
                while True:
                    chunk = fi.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    fo.write(chunk)
                    job.copiedBytes += len(chunk)
            shutil.copystat(s, d)
            if os.path.getsize(d) != os.path.getsize(s):
                raise RuntimeError(f"size mismatch after copy: {s}")
            job.filesDone += 1

        # Everything verified — remove the source
        if os.path.isfile(src):
            os.remove(src)
        else:
            shutil.rmtree(src)
        job.status = "done"
        logger.info("Move job %s done", job.id)
    except Exception as e:
        logger.exception("Move job %s failed", job.id)
        job.status = "failed"
        job.error = str(e)[:300]
    finally:
        job.finishedAt = time.time()


# ── HTTP handlers ────────────────────────────────────────────────────


sampler = Sampler()


async def health(request: web.Request) -> web.Response:
    return web.json_response({
        "status": "ok",
        "authenticated": bool(TOKEN),
        "drives": [d["name"] for d in DRIVES],
        "diskAccess": {d["name"]: DISK_ACCESS.get(d["path"]) for d in DRIVES},
        "pythonBin": PYTHON_BIN,
        "metricsAge": round(time.time() - sampler.metrics.get("sampledAt", 0), 1) if sampler.metrics else None,
    })


async def metrics(request: web.Request) -> web.Response:
    return web.json_response({
        **sampler.metrics,
        "containers": sampler.containers,
        "containersAt": sampler.containers_at or None,
    })


async def storage(request: web.Request) -> web.Response:
    if request.query.get("refresh") == "categories":
        asyncio.get_running_loop().run_in_executor(DU_EXECUTOR, sampler.sample_categories)
    return web.json_response(sampler.storage)


async def history(request: web.Request) -> web.Response:
    """Samples for the last N minutes (default 60, max 60)."""
    try:
        minutes = max(1, min(60, int(request.query.get("minutes", "60"))))
    except ValueError:
        minutes = 60
    since = time.time() - minutes * 60
    cores = psutil.cpu_count(logical=True) or 1
    return web.json_response({
        "intervalSeconds": METRICS_INTERVAL,
        "host": [
            {"t": round(t), "cpu": c, "memory": m, "swap": sw}
            for t, c, m, sw in sampler.history if t >= since
        ],
        "docker": [
            # docker stats reports CPU as % of one core summed; normalise to whole-machine %
            {"t": round(t), "cpu": round(c / cores, 1), "memory": mem}
            for t, c, mem in sampler.docker_history if t >= since
        ],
    })


def _trash_summary() -> dict[str, Any]:
    if not os.path.isdir(TRASH_DIR):
        return {"path": TRASH_DIR, "items": 0, "bytes": 0}
    names = [n for n in os.listdir(TRASH_DIR) if not n.startswith(".")]
    return {
        "path": TRASH_DIR,
        "items": len(names),
        "bytes": sum(_tree_size(os.path.join(TRASH_DIR, n)) for n in names),
    }


async def trash(request: web.Request) -> web.Response:
    return web.json_response(await asyncio.get_running_loop().run_in_executor(None, _trash_summary))


def _empty_trash() -> dict[str, Any]:
    """Delete everything inside TRASH_DIR. Refuses to touch anything else."""
    real = os.path.realpath(TRASH_DIR)
    if not real.endswith("/Trash") or not os.path.isdir(real):
        raise RuntimeError(f"refusing to empty {real}")
    if not _disk_ok(real):
        raise RuntimeError("no permission to read the drive")
    freed = 0
    removed = 0
    for n in os.listdir(real):
        if n.startswith("."):
            continue
        p = os.path.join(real, n)
        if os.path.islink(p):
            os.unlink(p)
            removed += 1
            continue
        freed += _tree_size(p)
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
        removed += 1
    logger.info("Emptied trash: %d item(s), %d bytes", removed, freed)
    return {"removed": removed, "freedBytes": freed}


async def empty_trash(request: web.Request) -> web.Response:
    try:
        result = await asyncio.get_running_loop().run_in_executor(MOVE_EXECUTOR, _empty_trash)
    except RuntimeError as e:
        raise web.HTTPServiceUnavailable(reason=str(e))
    return web.json_response(result)


async def start_move(request: web.Request) -> web.Response:
    body = await request.json()
    src = str(body.get("source", ""))
    dst = str(body.get("destination", ""))
    if not src or not dst:
        raise web.HTTPBadRequest(reason="source and destination are required")
    if not _within(src, MOVE_SOURCES):
        raise web.HTTPForbidden(reason=f"source must be under one of {MOVE_SOURCES}")
    if not _within(dst, MOVE_DESTINATIONS):
        raise web.HTTPForbidden(reason=f"destination must be under one of {MOVE_DESTINATIONS}")
    if not _disk_ok(src) or not _disk_ok(dst):
        raise web.HTTPServiceUnavailable(
            reason=f"agent has no permission to read that drive; grant Full Disk Access to {PYTHON_BIN}"
        )
    if not os.path.exists(src):
        raise web.HTTPNotFound(reason="source does not exist")
    if os.path.exists(dst) and os.path.isfile(src):
        raise web.HTTPConflict(reason="destination file already exists")
    for j in JOBS.values():
        if j.status in ("queued", "running") and j.source == src:
            return web.json_response(asdict(j), status=202)

    job = MoveJob(id=uuid.uuid4().hex[:12], source=src, destination=dst)
    JOBS[job.id] = job
    while len(JOBS) > MAX_JOBS:
        oldest = min(JOBS.values(), key=lambda j: j.startedAt)
        if oldest.status in ("queued", "running"):
            break
        del JOBS[oldest.id]
    asyncio.get_running_loop().run_in_executor(MOVE_EXECUTOR, _run_move, job)
    logger.info("Move job %s: %s -> %s", job.id, src, dst)
    return web.json_response(asdict(job), status=202)


async def list_jobs(request: web.Request) -> web.Response:
    jobs = sorted(JOBS.values(), key=lambda j: -j.startedAt)
    return web.json_response({"jobs": [asdict(j) for j in jobs]})


async def get_job(request: web.Request) -> web.Response:
    job = JOBS.get(request.match_info["id"])
    if not job:
        raise web.HTTPNotFound()
    return web.json_response(asdict(job))


# ── Lifecycle ────────────────────────────────────────────────────────


async def _loop(fn, interval: float, name: str, executor=None) -> None:
    loop = asyncio.get_running_loop()
    while True:
        try:
            await loop.run_in_executor(executor, fn)
        except Exception:
            logger.exception("%s sampler failed", name)
        await asyncio.sleep(interval)


async def on_startup(app: web.Application) -> None:
    psutil.cpu_percent(interval=None)  # prime the counters
    await asyncio.get_running_loop().run_in_executor(None, _probe_disk_access)
    app["tasks"] = [
        asyncio.create_task(_loop(_probe_disk_access, 60, "disk-access")),
        asyncio.create_task(_loop(sampler.sample_metrics, METRICS_INTERVAL, "metrics")),
        asyncio.create_task(_loop(sampler.sample_containers, DOCKER_STATS_INTERVAL, "docker")),
        asyncio.create_task(_loop(sampler.sample_storage, 30, "storage")),
        asyncio.create_task(_loop(sampler.sample_categories, DU_INTERVAL, "categories", DU_EXECUTOR)),
    ]


async def on_cleanup(app: web.Application) -> None:
    for t in app.get("tasks", []):
        t.cancel()


def make_app() -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get("/health", health)
    app.router.add_get("/metrics", metrics)
    app.router.add_get("/storage", storage)
    app.router.add_get("/history", history)
    app.router.add_get("/trash", trash)
    app.router.add_post("/trash/empty", empty_trash)
    app.router.add_post("/move", start_move)
    app.router.add_get("/jobs", list_jobs)
    app.router.add_get("/jobs/{id}", get_job)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    if not TOKEN:
        logger.error("HOST_AGENT_TOKEN is not set — every endpoint except /health will refuse requests")
    logger.info("host-agent listening on %s:%d (drives: %s)", HOST, PORT, ", ".join(d["name"] for d in DRIVES))
    web.run_app(make_app(), host=HOST, port=PORT, print=None)
