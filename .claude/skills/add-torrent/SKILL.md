---
name: add-torrent
description: Add a torrent to qBittorrent by searching Prowlarr indexers or fetching a magnet link from Nyaa. Use when the user wants to manually download a specific release that Sonarr/Radarr can't find automatically.
argument-hint: <search query or nyaa ID>
disable-model-invocation: true
---

# Add Torrent to qBittorrent

Add a torrent to qBittorrent by searching Prowlarr or fetching from Nyaa.

## Steps

1. **Determine the source** from `$ARGUMENTS`:
   - If it's a number, treat it as a Nyaa.si view ID
   - If it starts with `magnet:`, add it directly
   - Otherwise, search Prowlarr with it as a query

2. **Search Prowlarr** (if needed):
   - Get the Prowlarr API key: `docker exec prowlarr cat /config/config.xml` and extract the `<ApiKey>` value
   - Search: `curl -s "http://localhost:9696/api/v1/search?query=<url-encoded-query>&type=search" -H "X-Api-Key: <key>"`
   - Show the user the results (title, indexer, size, seeders) and ask them to pick one
   - Note: Prowlarr proxy download URLs (`http://localhost:9696/*/download?...`) are internal redirects and **cannot** be used directly as magnet links

3. **Get the real magnet link**:
   - If the result has an `infoUrl` or `guid` pointing to Nyaa (e.g. `https://nyaa.si/view/123456`), extract the ID and fetch from Nyaa
   - Fetch the Nyaa page: `curl -sL "https://nyaa.si/view/<id>"` and extract the magnet link with: `grep -oP 'magnet:\?xt=urn:btih:[^"]+' | head -1`
   - If not from Nyaa, try following the Prowlarr download URL to get the actual magnet/torrent

4. **Add to qBittorrent**:
   - Login: `curl -s -c /tmp/qbt_cookies.txt "http://localhost:8081/api/v2/auth/login" -d "username=admin&password=adminadmin"`
   - Add: `curl -s -b /tmp/qbt_cookies.txt "http://localhost:8081/api/v2/torrents/add" --data-urlencode "urls=<magnet_link>" -d "category=<category>"`
   - Default category is `tv` for series, `movies` for films, `ebooks` for books
   - Clean up: `rm -f /tmp/qbt_cookies.txt`

5. **Verify**: Wait a few seconds, then check the torrent was added:
   - `curl -s -b /tmp/qbt_cookies.txt "http://localhost:8081/api/v2/torrents/info"` and filter for the new torrent

## Important notes

- qBittorrent WebUI is on port **8081** (not 8080)
- Prowlarr proxy URLs are NOT real magnet links — always resolve to the actual magnet
- The `tv` category is what Sonarr monitors for auto-import
- The `movies` category is what Radarr monitors for auto-import
- Always use `--data-urlencode` for the magnet URL to handle special characters
- SSH to server: `ssh -i ~/.ssh/id_ed25519_homeserver 192.168.1.117`
