# 17 — Games site (games.noblehaus.uk)

One address for every game on the box: a hub page at **https://games.noblehaus.uk/** with a card
per game, and each game under its own path. A single Cloudflare route covers all of them, so
adding a game never touches Cloudflare. Script: `scripts/17-games.sh`. Config: `games/`.

| Game | Address | Runs as | Source |
|------|---------|---------|--------|
| Super Skidmarks | `/skidmarks/` | container `super-skidmarks` (LAN `:3002`) | `~/super-skidmarks` ← [noble1911/super-skidmarks](https://github.com/noble1911/super-skidmarks) |
| Word Poker | `/dont-lie/` | container `dont-lie-app` (LAN `:3001`) | `~/dont-lie` (not a git repo) |
| Gunpey 99 | `/gunpey/` | container `gunpey` (LAN `:3003`) | `~/gunpey` ← [noble1911/gunpey](https://github.com/noble1911/gunpey) |
| Tycoon Town | `/tycoon-town/` | container `tycoon-town` (LAN `:3005`) | `~/tycoon-town` ← `~/IdeaProjects/tycoon-town` on the laptop |
| Modern Combat | `/modern-combat/` | container `modern-combat` (LAN `:3004`) | `~/modern-combat` ← `~/IdeaProjects/modern-combat` ([noble1911/modern-combat](https://github.com/noble1911/modern-combat)) |
| Froths Party | `/froths/` | container `froths-party` (LAN `:3006`) | `~/froths-party` ← [noble1911/froths-party](https://github.com/noble1911/froths-party) (private) |

On the LAN the whole site is at `http://192.168.1.117:3010/`.

## How it works

```
browser ─https─▶ Cloudflare ─tunnel─▶ cloudflared ─http─▶ games-gateway (Caddy)
                                                           ├─ /               hub page (games/site/)
                                                           ├─ /skidmarks/*    → super-skidmarks:3002
                                                           ├─ /dont-lie/*     → dont-lie-app:80
                                                           ├─ /gunpey/*       → gunpey:3000
                                                           ├─ /modern-combat/* → modern-combat:3000
                                                           ├─ /tycoon-town/*  → tycoon-town:3000
                                                           └─ /froths/*       → froths-party:3000
```

- **The gateway strips the prefix.** A request for `/skidmarks/assets/app.js` reaches the game as
  `/assets/app.js`, so a game doesn't need to know where it's mounted. It only has to use relative
  URLs (see [Make it work under a path](#1-make-it-work-under-a-path)).
- **WebSockets pass straight through** (the multiplayer in skidmarks, gunpey, modern-combat, tycoon-town and froths), Cloudflare included.
- **`/<name>` redirects to `/<name>/`**: relative URLs resolve against the trailing slash.
- **A game that's down** (its container stopped) gets `games/site/down.html` with a 502, and its
  card on the hub says *Resting* instead of *Online*.
- **The hub** (`games/site/index.html`) draws a card for each entry in `games/site/games.json` and
  checks each game is answering.
- **Static games** (no server of their own) don't need a container: their files go in
  `~/games-static/<name>/`, which the gateway serves directly.

## One-time setup

1. **Start the gateway** on the server:

   ```bash
   cd ~/home-server && ./scripts/17-games.sh
   ```

   It creates `~/games-static`, starts `games-gateway` on the `homeserver` network, and prints
   which games answer. Re-run it any time; it reloads the gateway's config.

2. **Add the Cloudflare route** (once, ever): **Zero Trust → Networks → Tunnels →** your tunnel **→
   Configure → Public hostnames → Add a public hostname**:

   | Subdomain | Domain | Type | URL |
   |-----------|--------|------|-----|
   | `games` | `noblehaus.uk` | HTTP | `games-gateway:80` |

3. Open https://games.noblehaus.uk/. Every game's card should say *Online*.

## Adding a game

### 1. Make it work under a path

The game will be served at `https://games.noblehaus.uk/<name>/`, so nothing in it may assume it's at
the site's root:

- **Asset URLs relative**: `assets/app.js`, not `/assets/app.js`.
  - Vite: `base: './'` in `vite.config.js` (and copy that file into the Docker build).
  - Expo web: `"experiments": { "baseUrl": "/<name>" }` in `app.json`. This one is an absolute
    prefix, so also map `/<name>/` onto the site root in the game's own server so its LAN port keeps
    working (see `~/dont-lie/nginx.conf`).
  - Plain HTML: `src="app.js"`, `href="style.css"`, `new Audio('sfx/hit.wav')`.
- **Sockets and API calls next to the page**, not at the host's root:

  ```js
  const url = new URL('ws', location.href);            // …/<name>/ws
  url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(url.href);
  ```

  not `` new WebSocket(`wss://${location.host}/ws`) ``.
- **Links to its own pages** relative, or built from `location.pathname`.
- **Browser storage is shared.** Every game is on the same origin, so they share `localStorage`,
  cookies and IndexedDB. Prefix keys with the game (`skidmarks:settings`, `tycoon-town.save`).

### 2. Run it on the box

- **Game with a server:** a container on the shared network, restarting on its own:

  ```yaml
  services:
    mygame:
      build: .
      container_name: mygame
      ports:
        - "3007:3000"          # optional LAN port: take a free one from registry/services.yaml
      networks:
        - homeserver
      restart: unless-stopped
      healthcheck: …
  networks:
    homeserver:
      external: true
  ```

- **Static game:** copy its files to `~/games-static/<name>/`. No container.

### 3. Route it and list it

1. **`games/Caddyfile`**: add the route, next to the others:

   ```caddyfile
   redir /mygame /mygame/ 308
   handle_path /mygame/* {
   	reverse_proxy mygame:3000          # the container name and its port inside the network
   }
   ```

   For a static game, the block is `root * /srv/static/mygame` plus `file_server` instead of
   `reverse_proxy`.
2. **`games/site/games.json`**: add an entry. `path` is relative to the hub and ends in `/`:

   ```json
   {
     "id": "mygame",
     "name": "My Game",
     "path": "mygame/",
     "tagline": "One line on what you do in it.",
     "players": "Solo · up to 4 online",
     "image": "img/mygame.jpg"
   }
   ```

3. **`games/site/img/<id>.jpg`**: a 640×400 screenshot of the game's opening screen (a 1280×800
   capture at half size). Without one, the card shows the game's initial on a gradient.
4. **Apply it:** re-run `scripts/17-games.sh`. The hub's files are live as soon as they're
   copied; the Caddyfile needs the reload the script does.

### 4. Keep the registry honest

Add the game to `registry/REGISTRY.md` (Projects), its LAN port to `registry/services.yaml`, and a
row to the table at the top of this page. Run `registry/doctor.sh`.

## Updating a game

| Game | How |
|------|-----|
| Super Skidmarks | From the laptop, in the repo: `rsync -az --delete --exclude node_modules --exclude dist --exclude reference --exclude .venv-research --exclude __pycache__ --exclude .git --exclude '*.log' --exclude .DS_Store --exclude e2e/shots ./ 192.168.1.117:super-skidmarks/`, then on the box `cd ~/super-skidmarks && docker compose up -d --build`. Never copy `reference/` (the original game's data). |
| Word Poker | On the box: `cd ~/dont-lie && docker compose up -d --build`. Not a git repo: back files up before editing (the 2026-09-27 path change left copies in `.backup-2026-09-27/`). |
| Gunpey 99 | On the box: `cd ~/gunpey && git pull && docker compose up -d --build`. |
| Tycoon Town | From the laptop, a committed version: `rm -rf /tmp/tt && mkdir /tmp/tt && git archive HEAD \| tar -x -C /tmp/tt --exclude '*.blend' --exclude '*.jpg'`, then `rsync -az --delete /tmp/tt/ 192.168.1.117:tycoon-town/`, write `git rev-parse --short HEAD` to `~/tycoon-town/.deployed-commit`, then on the box `cd ~/tycoon-town && docker compose up -d --build`. A deploy restarts the container, which ends online games in progress. Full steps: the game repo's `CLAUDE.md`. |
| Modern Combat | From the laptop, a committed version: `npm run deploy` in the repo (`scripts/deploy.sh`: exports `HEAD` to `192.168.1.117:modern-combat/`, runs `docker compose up -d --build` there, waits for the healthcheck, then checks the page and a multiplayer socket through the gateway). No git on the box: `~/modern-combat/.deployed-commit` records which commit is live. |
| Froths Party | From the laptop, in the repo (the box can't pull the private repo): `rm -rf /tmp/froths && mkdir /tmp/froths && git archive HEAD \| tar -x -C /tmp/froths`, then `rsync -az --delete --exclude .env /tmp/froths/ 192.168.1.117:froths-party/`, then on the box `cd ~/froths-party && docker compose up -d --build`. Never overwrite `.env` (holds `PACKS_PASSWORD`); custom packs are in the `froths-party_froths-data` volume. |
| The hub | Edit `games/`, then re-run `scripts/17-games.sh`. |

## Testing

- **On the LAN:** http://192.168.1.117:3010/ is the whole site. `curl -I http://192.168.1.117:3010/<name>/`
  should give `200`.
- **Under a path, before the game ever reaches the box:** serve it behind anything that strips a
  prefix and check that its assets load and its socket connects. The gateway itself is the easiest.
- **Through Cloudflare, before a route exists:** a throwaway quick tunnel to the gateway:

  ```bash
  docker run -d --name games-quicktest --network homeserver cloudflare/cloudflared:2026.8.3 \
    tunnel --no-autoupdate --url http://games-gateway:80
  docker logs games-quicktest 2>&1 | grep trycloudflare.com   # the public URL
  docker rm -f games-quicktest                                # when done
  ```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Blank page; 404s for `/assets/…` or `/_expo/…` | Absolute asset URLs | Relative base: see [step 1](#1-make-it-work-under-a-path) |
| Game loads but multiplayer never connects | Socket URL built from `location.host` | Build it from `location.href` |
| "This game is taking a break" | The game's container is down | `docker ps -a`, `docker logs <container>` |
| Card says *Resting* but the game works on its LAN port | Wrong container name or port in the Caddyfile, or the container isn't on the `homeserver` network | `docker network inspect homeserver`; the port is the one *inside* the container |
| `/<name>/` works but `/<name>` (no slash) doesn't | No `redir` line | Add `redir /<name> /<name>/ 308` |
| Caddyfile change has no effect | Not reloaded | `docker exec games-gateway caddy reload --config /etc/caddy/Caddyfile` |
| A game's saves/settings clash with another's | Shared storage on one origin | Prefix the storage keys |

## Why paths, not a subdomain per game

A second-level name like `skidmarks.games.noblehaus.uk` needs Cloudflare's paid Advanced Certificate
Manager (the free certificate covers `*.noblehaus.uk` only). A first-level name per game works for
free but means a dashboard route per game (or a catch-all `*.noblehaus.uk` route sitting behind every
other hostname). Paths need one route, ever. The price is that games must be path-safe (step 1),
which in practice was two small edits per game.
