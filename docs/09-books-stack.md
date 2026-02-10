# Step 9: Deploy Books Stack

Deploy Audiobookshelf (ebooks + audiobooks) and Shelfarr (book search + download management).

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/09-books-stack.sh | bash
```

## Manual

### 1. Start Services

```bash
cd docker/books-stack
docker compose up -d
```

### 2. Verify Running

```bash
docker compose ps
```

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| Audiobookshelf | http://localhost:13378 | Ebook + audiobook library, reading, streaming |
| Shelfarr | http://localhost:5056 | Book search, download management, ABS auto-import |

## Initial Configuration

### Audiobookshelf

1. Open http://localhost:13378
2. Create admin account
3. **Add Libraries:**
   - Name: Audiobooks, Folder: `/audiobooks`, Media Type: Audiobooks
   - Name: eBooks, Folder: `/books`, Media Type: Books
4. **Install mobile apps:**
   - iOS: App Store "Audiobookshelf"
   - Android: Google Play "Audiobookshelf"
5. **Features:**
   - Built-in EPUB reader (browser-based)
   - Progress sync across devices
   - Offline downloads via mobile app
   - Sleep timer and playback speed control

### Shelfarr

1. Open http://localhost:5056
2. Create admin account
3. **Admin Settings > Prowlarr:**
   - URL: `http://prowlarr:9696`
   - API Key: (from Prowlarr > Settings > General)
4. **Admin Settings > Download Client:**
   - Type: qBittorrent
   - URL: `http://qbittorrent:8081`
   - Username: `admin`
   - Password: (your qBittorrent password)
5. **Admin Settings > Audiobookshelf:**
   - URL: `http://audiobookshelf:80`
   - API Token: (from ABS > Settings > Users > your admin user)

## Volume Mappings

| Service | Container Path | Host Path |
|---------|----------------|-----------|
| Audiobookshelf | `/audiobooks` | `/Volumes/HomeServer/Books/Audiobooks` |
| Audiobookshelf | `/books` | `/Volumes/HomeServer/Books/eBooks` |
| Shelfarr | `/audiobooks` | `/Volumes/HomeServer/Books/Audiobooks` |
| Shelfarr | `/ebooks` | `/Volumes/HomeServer/Books/eBooks` |
| Shelfarr | `/downloads` | `/Volumes/HomeServer/Downloads` |

## The Book Download Flow

```
Search in Shelfarr (or ask Butler AI)
       ↓
Prowlarr provides indexers
       ↓
qBittorrent downloads to /Downloads
       ↓
Shelfarr organizes files by author/title
       ↓
Shelfarr imports into Audiobookshelf
       ↓
ABS shows book in library (ebook reader + mobile apps)
```

Butler's BookTool can also trigger downloads via voice/chat:
```
"Find me the new Dune audiobook"
       ↓
BookTool → Open Library (metadata) → Prowlarr (torrent) → qBittorrent
       ↓
Shelfarr picks up completed download → organizes → ABS import
```

## Docker Commands

```bash
# View logs
docker logs audiobookshelf
docker logs shelfarr

# Restart
cd docker/books-stack
docker compose restart

# Update
docker compose pull
docker compose up -d
```

## Troubleshooting

### Audiobookshelf not detecting books

- Check folder structure: `/audiobooks/Author/Book Title/`
- Audiobooks should have audio files (.m4b, .mp3, etc.)
- Use "Scan" button in library settings

### Shelfarr search returns no results

- Verify Prowlarr connection in Admin Settings
- Check that Prowlarr has indexers configured (see [Prowlarr Indexer Setup](./prowlarr-indexers.md))
- Try a broader search query

### Downloads stuck or failing

- Check qBittorrent at http://localhost:8081 for download status
- Verify qBittorrent connection in Shelfarr Admin Settings
- Check torrent indexer health in Prowlarr

## Related Guides

- [Ebook Reading Guide](./ebook-reading-guide.md) — Read your library on phones, tablets, and e-readers
- [Prowlarr Indexer Setup](./prowlarr-indexers.md) — Configure indexers for book search

## Next Step

→ [Step 10: Deploy Photos & Files](./10-photos-files.md)
