# Step 9: Deploy Books Stack

Deploy Audiobookshelf (ebooks + audiobooks) and LazyLibrarian (book search + download management).

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
| LazyLibrarian | http://localhost:5299 | Book search, download management, library organization |

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

### LazyLibrarian

1. Open http://localhost:5299
2. **Config > Downloaders > qBittorrent:**
   - Host: `qbittorrent`
   - Port: `8081`
   - Username: `admin`
   - Password: (your qBittorrent password)
3. **Config > Processing:**
   - eBook destination: `/books`
   - Audiobook destination: `/audiobooks`
4. **In Prowlarr** (http://localhost:9696):
   - Settings > Apps > Add > LazyLibrarian
   - URL: `http://lazylibrarian:5299`
   - API Key: (from LazyLibrarian Config > Interface)

## Volume Mappings

| Service | Container Path | Host Path |
|---------|----------------|-----------|
| Audiobookshelf | `/audiobooks` | `/Volumes/HomeServer/Books/Audiobooks` |
| Audiobookshelf | `/books` | `/Volumes/HomeServer/Books/eBooks` |
| LazyLibrarian | `/audiobooks` | `/Volumes/HomeServer/Books/Audiobooks` |
| LazyLibrarian | `/books` | `/Volumes/HomeServer/Books/eBooks` |
| LazyLibrarian | `/downloads` | `/Volumes/HomeServer/Downloads` |

## The Book Download Flow

```
Search in LazyLibrarian (or ask Butler AI)
       ↓
Prowlarr provides indexers
       ↓
qBittorrent downloads to /Downloads
       ↓
LazyLibrarian organizes files by author/title
       ↓
Files moved to /books or /audiobooks
       ↓
ABS shows book in library (ebook reader + mobile apps)
```

Butler's BookTool can also trigger downloads via voice/chat:
```
"Find me the new Dune audiobook"
       ↓
BookTool → Open Library (metadata) → Prowlarr (torrent) → qBittorrent
       ↓
LazyLibrarian picks up completed download → organizes → ABS import
```

## Docker Commands

```bash
# View logs
docker logs audiobookshelf
docker logs lazylibrarian

# Restart
cd docker/books-stack
docker compose restart

# Update
docker compose pull
docker compose up -d
```

## Troubleshooting

### LazyLibrarian search returns no results

- Verify Prowlarr has synced indexers to LazyLibrarian (Prowlarr > Settings > Apps)
- Check that Prowlarr has indexers configured (see [Prowlarr Indexer Setup](./prowlarr-indexers.md))
- Try a broader search query

### Downloads stuck or failing

- Check qBittorrent at http://localhost:8081 for download status
- Verify qBittorrent connection in LazyLibrarian Config > Downloaders
- Check torrent indexer health in Prowlarr

### Audiobookshelf not detecting books

- Check folder structure: `/audiobooks/Author/Book Title/`
- Audiobooks should have audio files (.m4b, .mp3, etc.)
- Use "Scan" button in library settings

## Related Guides

- [Ebook Reading Guide](./ebook-reading-guide.md) — Read your library on phones, tablets, and e-readers
- [Prowlarr Indexer Setup](./prowlarr-indexers.md) — Configure indexers for book search

## Next Step

→ [Step 10: Deploy Photos & Files](./10-photos-files.md)
