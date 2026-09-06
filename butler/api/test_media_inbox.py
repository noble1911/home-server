"""Tests for the media inbox matching logic (no network, no filesystem)."""

from __future__ import annotations

from .media_inbox import _radarr_file, _sonarr_file, _summarise


def _sonarr_item(ok: bool = True, rej: list[str] | None = None) -> dict:
    return {
        "path": "/downloads/Complete/Show.S01E01.mkv",
        "relativePath": "Show.S01E01.mkv",
        "series": {"id": 7, "title": "Show"} if ok else None,
        "episodes": [{"id": 101}] if ok else [],
        "quality": {"quality": {"name": "WEBDL-1080p"}},
        "languages": [{"id": 1, "name": "English"}],
        "releaseGroup": "GRP",
        "rejections": [{"reason": r} for r in (rej or [])],
    }


class TestSummarise:
    def test_fully_matched_series(self):
        s = _summarise("sonarr", [_sonarr_item(), _sonarr_item()])
        assert s["matched"] == s["files"] == 2
        assert s["titles"] == ["Show"] and s["episodes"] == 2
        assert s["rejections"] == []

    def test_rejection_blocks_match(self):
        s = _summarise("sonarr", [_sonarr_item(), _sonarr_item(rej=["Sample file"])])
        assert s["files"] == 2 and s["matched"] == 1
        assert s["rejections"] == ["Sample file"]

    def test_unknown_movie(self):
        r = _summarise("radarr", [{"path": "/x", "relativePath": "x", "movie": None,
                                   "rejections": [{"reason": "Unknown Movie"}]}])
        assert r["matched"] == 0 and r["rejections"] == ["Unknown Movie"] and r["titles"] == []


class TestCommandPayloads:
    def test_sonarr_file_shape(self):
        f = _sonarr_file(_sonarr_item())
        assert f["seriesId"] == 7 and f["episodeIds"] == [101]
        assert f["path"].startswith("/downloads/Complete/")
        assert f["releaseType"] == "unknown" and f["indexerFlags"] == 0

    def test_radarr_file_shape(self):
        f = _radarr_file({"path": "/downloads/Complete/M.mkv", "movie": {"id": 3},
                          "quality": {}, "languages": [], "releaseGroup": None})
        assert f["movieId"] == 3 and f["releaseGroup"] == "" and f["languages"] == []
