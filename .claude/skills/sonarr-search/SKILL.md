---
name: sonarr-search
description: Search, rescan, or check status of series in Sonarr. Use when the user wants to trigger a search for a series, check episode status, or rescan disk for existing files.
argument-hint: <search|rescan|status|list> [series name] [season]
disable-model-invocation: true
---

# Sonarr Series Management

Manage series in Sonarr — search for downloads, rescan disk, check status.

## Setup

SSH into the server: `ssh -i ~/.ssh/id_ed25519_homeserver 192.168.1.117`

Prefix commands with: `export PATH=$PATH:/opt/orbstack/bin:/usr/local/bin`

Get Sonarr API key: `docker exec sonarr cat /config/config.xml` → extract `<ApiKey>`

Base URL: `http://localhost:8989/api/v3`

## Actions

### Search for downloads

1. Find the series: `curl -s "http://localhost:8989/api/v3/series" -H "X-Api-Key: <key>"` and match by title
2. If a season is specified, search that season:
   ```
   curl -s -X POST "http://localhost:8989/api/v3/command" -H "X-Api-Key: <key>" -H "Content-Type: application/json" -d '{"name":"SeasonSearch","seriesId":<id>,"seasonNumber":<n>}'
   ```
3. If no season specified, search all monitored:
   ```
   curl -s -X POST "http://localhost:8989/api/v3/command" -H "X-Api-Key: <key>" -H "Content-Type: application/json" -d '{"name":"SeriesSearch","seriesId":<id>}'
   ```

**Warning:** Searching triggers many indexer API calls. For anime with many episodes, search ONE season at a time to avoid rate-limiting indexers (429 errors) which can destabilize the Cloudflare tunnel.

### Rescan disk

Trigger a disk scan to pick up files that were added outside Sonarr:
```
curl -s -X POST "http://localhost:8989/api/v3/command" -H "X-Api-Key: <key>" -H "Content-Type: application/json" -d '{"name":"RescanSeries","seriesId":<id>}'
```

Note: If files were downloaded outside Sonarr, the naming may not match Sonarr's expected format. The user may need to do a Manual Import from the Sonarr UI.

### Check status

Show per-season breakdown:
```
curl -s "http://localhost:8989/api/v3/series/<id>" -H "X-Api-Key: <key>"
```
For each season, show: season number, monitored status, episodes on disk vs total.

### List all series

```
curl -s "http://localhost:8989/api/v3/series" -H "X-Api-Key: <key>"
```
Show each series with title and episode file count vs total.

## Common issues

- **Anime episode mapping**: Sonarr uses TVDB numbering which can differ from scene numbering. Releases may be rejected as "Unknown Series" or "Episode wasn't requested"
- **Language profile**: The deprecated language profile may block Japanese-only releases. Check via `curl -s "http://localhost:8989/api/v3/languageprofile" -H "X-Api-Key: <key>"` — if only English is allowed, update to include Japanese and Any
- **Rate limiting**: Indexers return 429 errors when hammered. Search one season at a time for large series
- **File recognition**: Files added outside Sonarr may need Manual Import from the UI if filenames don't match TVDB naming
