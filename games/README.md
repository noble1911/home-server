# games/ — games.noblehaus.uk

The games site: a hub page at https://games.noblehaus.uk/ and every game under its own path,
behind one Caddy container (`games-gateway`, LAN :3010). **Full guide: `docs/17-games.md`.**

| File | What |
|------|------|
| `Caddyfile` | one route per game (`handle_path /<name>/* { reverse_proxy <container>:<port> }`, or `file_server` for static games) |
| `site/games.json` | the hub's list of games (name, path, tagline, players, image) |
| `site/index.html` | the hub page; `site/down.html` is shown when a game's container is down |
| `site/img/<id>.jpg` | 640×400 screenshots for the hub cards |
| `docker-compose.yml` | the gateway; mounts `~/games-static` for static games |

| Game | Path | Where it lives | Update it |
|------|------|----------------|-----------|
| Super Skidmarks | `/skidmarks/` | `super-skidmarks` :3002, `~/super-skidmarks` | rsync from the laptop repo, `docker compose up -d --build` |
| Word Poker | `/dont-lie/` | `dont-lie-app` :3001, `~/dont-lie` (no git) | `docker compose up -d --build` in `~/dont-lie` |
| Gunpey 99 | `/gunpey/` | `gunpey` :3003, `~/gunpey` | `git pull && docker compose up -d --build` |
| Tycoon Town | `/tycoon-town/` | static, `~/games-static/tycoon-town` | copy a commit's game files from the laptop |

**Add a game:** make it work under a path (relative asset and socket URLs, prefixed storage keys),
run it on the `homeserver` network (or drop static files in `~/games-static/<name>/`), add its route
here and its entry in `site/games.json`, then `../scripts/17-games.sh`. No Cloudflare change: the
tunnel sends all of `games.noblehaus.uk` to this gateway.

**Apply changes:** `../scripts/17-games.sh` (starts the gateway, reloads the Caddyfile, checks each game).
