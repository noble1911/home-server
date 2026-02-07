# Step 9: Deploy Books Stack

Deploy Calibre-Web (ebooks), Audiobookshelf (audiobooks), and Readarr (automation).

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
| Calibre-Web | http://localhost:8083 | E-book library & Kindle sync |
| Audiobookshelf | http://localhost:13378 | Audiobook streaming |
| Readarr | http://localhost:8787 | Book/audiobook automation |

## Initial Configuration

### Calibre-Web

1. Open http://localhost:8083
2. Login: `admin` / `admin123`
3. **First-time setup:**
   - Database path: `/books/Calibre Library/metadata.db`
   - If no Calibre library exists yet, you'll need to create one first
4. **Admin > Edit Basic Configuration:**
   - Enable uploads
   - Configure Kindle email (for Send to Kindle)
5. **Change the default password!**

#### Creating a Calibre Library (if new)

If you don't have an existing Calibre library:

```bash
# Install Calibre on your Mac temporarily
brew install --cask calibre

# Create a library at your external drive
# Open Calibre, set library location to /Volumes/HomeServer/Books/eBooks/Calibre Library
# Add a few books, then close Calibre
```

### Audiobookshelf

1. Open http://localhost:13378
2. Create admin account
3. **Add Library:**
   - Name: Audiobooks
   - Folders: `/audiobooks`
   - Media Type: Audiobooks
4. **Install mobile apps:**
   - iOS: App Store "Audiobookshelf"
   - Android: Google Play "Audiobookshelf"
5. **Features:**
   - Progress sync across devices
   - Offline downloads
   - Sleep timer
   - Playback speed control

### Readarr

1. Open http://localhost:8787
2. **Settings > Media Management:**
   - Add Root Folder: `/books/eBooks` (for ebooks)
   - Add Root Folder: `/books/Audiobooks` (for audiobooks)
3. **Settings > Download Clients:**
   - Add qBittorrent:
     - Host: `qbittorrent`
     - Port: `8081`
     - Category: `books`
4. **Settings > General:**
   - Copy API Key for Prowlarr

### Connect to Prowlarr

In Prowlarr (http://localhost:9696):

1. **Settings > Apps > Add Application:**
   - **Readarr:**
     - Prowlarr Server: `http://prowlarr:9696`
     - Readarr Server: `http://readarr:8787`
     - API Key: (from Readarr)

## Volume Mappings

| Service | Container Path | Host Path |
|---------|----------------|-----------|
| Calibre-Web | `/books` | `/Volumes/HomeServer/Books/eBooks` |
| Audiobookshelf | `/audiobooks` | `/Volumes/HomeServer/Books/Audiobooks` |
| Audiobookshelf | `/books` | `/Volumes/HomeServer/Books/eBooks` |
| Readarr | `/books` | `/Volumes/HomeServer/Books` |
| Readarr | `/downloads` | `/Volumes/HomeServer/Downloads` |

## The Book Download Flow

```
Search in Readarr
       ↓
Prowlarr provides indexers
       ↓
Readarr sends to qBittorrent
       ↓
qBittorrent downloads to /Downloads/Complete/Books
       ↓
Readarr moves to /Books/eBooks or /Books/Audiobooks
       ↓
Calibre-Web or Audiobookshelf shows in library
```

## Send to Kindle

Calibre-Web can send ebooks directly to your Kindle with one click. This requires:
1. SMTP email settings configured in Calibre-Web (Gmail App Password)
2. Your Kindle email address set in your user profile
3. Your sending email approved in Amazon's settings

See the **[Kindle Email Delivery Setup Guide](./kindle-email-setup.md)** for full step-by-step instructions.

> **Quick start:** If you added `CALIBRE_SMTP_*` variables to `~/.homeserver-credentials` before running setup, SMTP is already configured. Just set your Kindle email in your Calibre-Web profile.
>
> The variables are: `CALIBRE_SMTP_SERVER`, `CALIBRE_SMTP_PORT` (default: 587), `CALIBRE_SMTP_ENCRYPTION` (1=STARTTLS), `CALIBRE_SMTP_LOGIN`, `CALIBRE_SMTP_PASSWORD`, `CALIBRE_SMTP_FROM`. See the [Kindle Email Delivery guide](./kindle-email-setup.md) for details.

## Docker Commands

```bash
# View logs
docker logs calibre-web
docker logs audiobookshelf
docker logs readarr

# Restart
cd docker/books-stack
docker compose restart

# Update
docker compose pull
docker compose up -d
```

## Troubleshooting

### Calibre-Web can't find database

The `metadata.db` file must exist. Either:
- Copy an existing Calibre library
- Create one with Calibre desktop app first

### Audiobookshelf not detecting books

- Check folder structure: `/audiobooks/Author/Book Title/`
- Audiobooks should have audio files (.m4b, .mp3, etc.)
- Use "Scan" button in library settings

### Readarr shows "No root folders"

Add root folders in Settings > Media Management before searching for books.

## Related Guides

- [Ebook Reading Guide](./ebook-reading-guide.md) — Read your library on phones, tablets, and e-readers
- [OPDS Feed Setup](./opds-setup.md) — Connect mobile reading apps to browse and download books
- [Kindle Email Delivery](./kindle-email-setup.md) — Send books directly to your Kindle
- [Prowlarr Indexer Setup](./prowlarr-indexers.md) — Configure indexers for Readarr book search

## Next Step

→ [Step 10: Deploy Photos & Files](./10-photos-files.md)
