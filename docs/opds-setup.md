# OPDS Feed Setup Guide

Configure Calibre-Web's OPDS catalog feed so mobile reading apps can browse and download books directly — no browser needed.

> **Prerequisites:** Calibre-Web is running ([Step 9](./09-books-stack.md)) and you've completed initial setup at http://localhost:8083.

## What is OPDS?

OPDS (Open Publication Distribution System) is a catalog format that ebook apps understand natively. Once enabled, apps like KOReader, Moon+ Reader, and FBReader can:

- Browse your full library by author, category, or series
- Search for specific titles
- Download books directly to the device
- Access your library from anywhere via Tailscale

Think of it as an RSS feed for your ebook collection.

## 1. Enable OPDS in Calibre-Web

1. Open http://localhost:8083
2. Log in as the admin user
3. Go to **Admin** → **Edit Basic Configuration** → **Feature Configuration**
4. Check **Enable OPDS feed**
5. Click **Save**

### Create a User for OPDS Access

If you don't want to use the admin account from mobile apps, create a dedicated user:

1. Go to **Admin** → **Add New User**
2. Set a username and password
3. Under **Allow Downloads**, ensure it's enabled
4. Click **Save**

> **Tip:** Each person in the household should have their own user — this keeps reading lists, bookmarks, and preferences separate.

## 2. OPDS Endpoint URLs

Once enabled, the OPDS feed is available at:

| Access Method | URL |
|--------------|-----|
| Local network | `http://localhost:8083/opds` |
| Tailscale (remote) | `http://<tailscale-ip>:8083/opds` |
| Tailscale MagicDNS | `http://mac-mini:8083/opds` |

To find your Tailscale IP:

```bash
tailscale ip -4
# Returns something like 100.x.y.z
```

> **Note:** OPDS uses HTTP Basic Authentication — your Calibre-Web username and password protect the feed. When connecting from outside your home, always use Tailscale rather than exposing port 8083 to the internet.

## 3. Connect Mobile Apps

### KOReader (Android / Linux e-ink devices)

KOReader is the best choice for e-ink devices (Kindle, Kobo, PocketBook running KOReader firmware).

1. Open KOReader
2. Tap the **top menu bar** → **Search** → **OPDS catalog**
3. Tap **+** to add a new catalog
4. Enter:
   - **Catalog name:** Home Library
   - **Catalog URL:** `http://<tailscale-ip>:8083/opds`
5. When prompted, enter your Calibre-Web **username** and **password**
6. Browse your library, tap a book, and choose a format to download

### Moon+ Reader (Android)

1. Open Moon+ Reader
2. Tap **Net Library** (book icon with globe)
3. Tap **OPDS catalog**
4. Tap **+** (Add) at the top
5. Enter:
   - **Name:** Home Library
   - **URL:** `http://<tailscale-ip>:8083/opds`
   - **Username:** your Calibre-Web username
   - **Password:** your Calibre-Web password
6. Tap **OK**
7. Browse and tap any book to download and open it

### FBReader (Android / iOS)

1. Open FBReader
2. Go to **Menu** → **Network Library** → **Add catalog**
3. Enter:
   - **Title:** Home Library
   - **URL:** `http://<tailscale-ip>:8083/opds`
   - **User name:** your Calibre-Web username
   - **Password:** your Calibre-Web password
4. Tap **OK** or **Add**
5. The catalog appears in your Network Library — tap to browse

### Panels (iOS)

Panels is a good OPDS client for iPhone and iPad, especially for comics and manga.

1. Open Panels
2. Tap **Library** → **Add OPDS Feed**
3. Enter:
   - **Name:** Home Library
   - **URL:** `http://<tailscale-ip>:8083/opds`
   - **Username:** your Calibre-Web username
   - **Password:** your Calibre-Web password
4. Tap **Save**
5. Browse your library under the OPDS section

### Cantook / Other iOS Readers

Many iOS ebook readers support OPDS. The general setup pattern is:

1. Look for **Add catalog**, **OPDS**, or **Network Library** in the app's settings
2. Enter the URL: `http://<tailscale-ip>:8083/opds`
3. Enter Calibre-Web credentials when prompted

## 4. Verify It Works

After connecting an app, confirm these work:

| Feature | How to Test |
|---------|-------------|
| **Browse** | Open the OPDS catalog — you should see categories (Authors, Series, etc.) |
| **Search** | Use the app's search within the catalog — results should return |
| **Download** | Tap a book and download it — the file should transfer to your device |
| **Formats** | Check that EPUB, PDF, and other formats you've uploaded are available |

> **Tip:** If you only see a few books, make sure your Calibre library has been populated. Calibre-Web reads from the `metadata.db` in your Calibre library directory.

## 5. Remote Access via Tailscale

OPDS works seamlessly over Tailscale, giving you access to your library from anywhere:

1. Install Tailscale on your mobile device ([iOS](https://apps.apple.com/app/tailscale/id1470499037) / [Android](https://play.google.com/store/apps/details?id=com.tailscale.ipn))
2. Sign in with the same account as your server
3. Use the Tailscale IP or MagicDNS hostname in your OPDS URL
4. Books download directly to your phone — no cloud storage needed

### Speed Expectations

| Connection | Speed |
|-----------|-------|
| Same Wi-Fi network | Near-instant downloads |
| Tailscale (remote) | Depends on your home upload speed; typical ebooks (1-5 MB) download in seconds |
| Large PDFs / comics | May take longer on slower connections |

## Troubleshooting

### "Authentication required" or 401 error

- Double-check your Calibre-Web username and password
- Ensure the user account has **Allow Downloads** enabled
- Some apps need you to enter credentials in the catalog settings, not at the prompt

### OPDS catalog shows but no books appear

- Verify Calibre-Web can see your library at http://localhost:8083
- Check that the library has books with downloadable formats (EPUB, PDF, etc.)
- Refresh the catalog in your app — some apps cache empty results

### "Connection refused" or timeout

- **On local network:** Confirm Calibre-Web is running: `docker ps | grep calibre-web`
- **Over Tailscale:** Verify Tailscale is connected on both devices: `tailscale status`
- **Port check:** Ensure port 8083 is mapped: `docker port calibre-web`

### App doesn't show OPDS option

- Some free reader apps restrict OPDS to their paid/pro version
- Check the app's documentation for OPDS support
- Try one of the apps listed above — they all have confirmed OPDS support

### Books download but won't open

- Check the file format — some readers only support EPUB, not MOBI or AZW3
- Use Calibre-Web's built-in conversion (if the `universal-calibre` mod is installed) to convert books to EPUB
- The Docker Compose includes `DOCKER_MODS=linuxserver/mods:universal-calibre`, which enables format conversion

### Search returns no results

- OPDS search uses Calibre-Web's search, which queries the metadata database
- Ensure book metadata (title, author) is correct in Calibre-Web
- Try searching by exact title or author name

## Next Steps

- [Step 9: Books Stack](./09-books-stack.md) — Full Calibre-Web setup and configuration
- [Kindle Email Delivery](./kindle-email-setup.md) — Send books directly to your Kindle (Issue #112)
