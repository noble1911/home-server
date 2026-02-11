# Ebook Reading Guide

How to read ebooks and audiobooks from your home server on phones, tablets, and e-readers.

> **Prerequisites:** Books stack is running ([Step 9](./09-books-stack.md)) and you've added some books to your library.

## Quick Overview

Your server provides multiple ways to read on mobile — pick the one that fits your workflow:

| Method | Best For | Requires App Install? |
|--------|----------|----------------------|
| [Browser reader](#1-read-in-the-browser) | Quick reads, any device | No |
| [Download & read](#2-download-and-read-locally) | Offline reading, best reading experience | Yes (any reader app) |
| [Audiobookshelf app](#3-audiobooks-and-ebooks-with-audiobookshelf) | Audiobooks, ebooks, and progress sync | Yes (Audiobookshelf app) |

## 1. Read in the Browser

Audiobookshelf has a built-in EPUB reader — no app needed. This works on any device with a browser.

1. Open Audiobookshelf:
   - **Home network:** http://localhost:13378
   - **Remote:** `https://books.yourdomain.com` (via Cloudflare Tunnel)
2. Log in with your credentials
3. Navigate to your eBooks library
4. Click a book and use the built-in reader

### What the browser reader supports

- EPUB rendering with adjustable fonts and margins
- Dark and light reading modes
- Reading position saved per user account
- Works on iPhone, iPad, Android phones and tablets

> **Tip:** The browser reader works well for quick reads, but for long sessions a dedicated reader app gives a better experience (font rendering, page animations, dictionary lookup).

## 2. Download and Read Locally

Download books from Audiobookshelf to your phone, then open them in your preferred reader app.

1. Open Audiobookshelf in your mobile browser
2. Find a book and tap its cover
3. Download the book file (EPUB is best for most readers)
4. Open the downloaded file — your phone will offer to open it in a compatible app

### Recommended Reader Apps

| App | Platform | Highlights |
|-----|----------|------------|
| **Apple Books** | iOS / macOS | Built-in, no install needed, great EPUB support |
| **KOReader** | Android / e-ink devices | Open source, highly customizable, supports e-ink |
| **Moon+ Reader** | Android | Beautiful UI, extensive customization |
| **FBReader** | Android / iOS | Lightweight, supports many formats |
| **Librera Reader** | Android | Free, handles PDF and DJVU well alongside EPUB |

## 3. Audiobooks and Ebooks with Audiobookshelf

Audiobookshelf has dedicated mobile apps with features like progress sync, offline downloads, sleep timer, and playback speed control. It serves both audiobooks and ebooks from the same app.

1. Install the app:
   - **iOS:** Search "Audiobookshelf" in the App Store
   - **Android:** Search "Audiobookshelf" in Google Play
2. Open the app and enter your server address:
   - **Home network:** `http://localhost:13378`
   - **Remote:** `https://books.yourdomain.com` (via Cloudflare Tunnel)
3. Log in with your Audiobookshelf credentials
4. Browse your library, download books for offline listening/reading, and your progress syncs automatically

## 4. Remote Access

All methods above work from outside your home network using Cloudflare Tunnel.

| Service | Remote URL |
|---------|-----------|
| Audiobookshelf | `https://books.yourdomain.com` |
| LazyLibrarian | `https://lazylibrarian.yourdomain.com` |

Replace `yourdomain.com` with the domain you configured in your Cloudflare Tunnel.

## Choosing a Method

| Scenario | Recommended Method |
|----------|-------------------|
| "I just want to read a chapter quickly" | Browser reader in ABS |
| "I read a lot and want the best experience" | Download + dedicated reader app |
| "I'm going on a flight with no internet" | Download to device beforehand |
| "I listen to audiobooks on my commute" | Audiobookshelf app |
| "I have an e-ink Kindle or Kobo" | Download EPUB and sideload |

## Troubleshooting

### Can't connect remotely

- **Cloudflare Tunnel:** Verify the tunnel is running: `docker logs cloudflared`
- Confirm Audiobookshelf is running: `docker ps | grep audiobookshelf`

### Downloaded book won't open

- Check the format — most mobile readers handle EPUB best
- If the file is DRM-protected, it won't open in third-party readers

### Reading progress not syncing

- **Audiobookshelf:** Progress syncs automatically when connected. If offline, it syncs when you reconnect
- **Downloaded files:** No sync — books are standalone files on your device

## Related Guides

- [Step 9: Books Stack](./09-books-stack.md) — Audiobookshelf and LazyLibrarian setup
- [Prowlarr Indexer Setup](./prowlarr-indexers.md) — Configure indexers for book search
