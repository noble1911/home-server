# Step 9: Deploy Books Stack

Deploy Audiobookshelf (ebooks + audiobooks). New books come from asking Butler, which downloads them straight into the library folders.

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

## Volume Mappings

| Service | Container Path | Host Path |
|---------|----------------|-----------|
| Audiobookshelf | `/audiobooks` | `/Volumes/HomeServer/Books/Audiobooks` |
| Audiobookshelf | `/books` | `/Volumes/HomeServer/Books/eBooks` |
| qBittorrent | `/audiobooks` | `/Volumes/HomeServer/Books/Audiobooks` |
| qBittorrent | `/ebooks` | `/Volumes/HomeServer/Books/eBooks` |

## The Book Download Flow

Ask Butler by chat or voice:
```
"Find me the new Dune audiobook"
       ↓
BookTool → Open Library (metadata) → Prowlarr (torrent search)
       ↓
qBittorrent saves straight into /ebooks or /audiobooks
       ↓
Audiobookshelf shows the book in its library (ebook reader + mobile apps)
```

LazyLibrarian used to sit alongside this; it was removed on 2026-10-30
(not useful, and it had no working login).

## Docker Commands

```bash
# View logs
docker logs audiobookshelf

# Restart
cd docker/books-stack
docker compose restart

# Update
docker compose pull
docker compose up -d
```

## Troubleshooting

### Butler can't find a book

- Check that Prowlarr has indexers configured (see [Prowlarr Indexer Setup](./prowlarr-indexers.md))
- Try a broader search query

### Downloads stuck or failing

- Check qBittorrent at http://localhost:8081 for download status
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
