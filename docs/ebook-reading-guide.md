# Ebook Reading Guide

How to read ebooks and audiobooks from your home server on phones, tablets, and e-readers.

> **Prerequisites:** Books stack is running ([Step 9](./09-books-stack.md)) and you've added some books to your Calibre library.

## Quick Overview

Your server provides multiple ways to read on mobile — pick the one that fits your workflow:

| Method | Best For | Requires App Install? |
|--------|----------|----------------------|
| [Browser reader](#1-read-in-the-browser) | Quick reads, any device | No |
| [Download & read](#2-download-and-read-locally) | Offline reading, best reading experience | Yes (any reader app) |
| [OPDS feed](#3-opds-feed) | Power users, syncing libraries to reader apps | Yes (OPDS-capable app) |
| [Audiobookshelf app](#4-audiobooks-with-audiobookshelf) | Audiobooks and podcasts | Yes (Audiobookshelf app) |

## 1. Read in the Browser

Calibre-Web has a built-in EPUB and PDF reader — no app needed. This works on any device with a browser.

1. Open Calibre-Web:
   - **Home network:** http://localhost:8083
   - **Remote:** `https://books.yourdomain.com` (via Cloudflare Tunnel)
2. Log in with your Calibre-Web credentials
3. Find a book and click its cover
4. Click **Read in Browser** (EPUB) or **Read in Browser** (PDF)

### What the browser reader supports

- Page turning with swipe or tap
- Adjustable font size and margins
- Light and dark reading modes
- Bookmarks and reading position memory (per user account)
- Works on iPhone, iPad, Android phones and tablets

> **Tip:** The browser reader works well for quick reads, but for long sessions a dedicated app gives a better experience (font rendering, page animations, dictionary lookup).

## 2. Download and Read Locally

Download books from Calibre-Web to your phone, then open them in your preferred reader app.

1. Open Calibre-Web in your mobile browser
2. Find a book and tap its cover
3. Tap the **download** button and choose a format (EPUB is best for most readers)
4. Open the downloaded file — your phone will offer to open it in a compatible app

### Recommended Reader Apps

| App | Platform | Highlights |
|-----|----------|------------|
| **Apple Books** | iOS / macOS | Built-in, no install needed, great EPUB support |
| **KOReader** | Android / e-ink devices | Open source, highly customizable, supports e-ink |
| **Moon+ Reader** | Android | Beautiful UI, extensive customization, OPDS support |
| **FBReader** | Android / iOS | Lightweight, supports many formats |
| **Librera Reader** | Android | Free, handles PDF and DJVU well alongside EPUB |

> **Format tip:** If a book isn't available in EPUB, Calibre-Web can convert it on the fly. Click the **Convert** button on the book's detail page (requires the `universal-calibre` Docker mod, which is included in our setup).

## 3. OPDS Feed

OPDS lets reader apps connect directly to your library — browse, search, and download books without opening a browser. This is the most seamless mobile experience.

**Full setup instructions:** [OPDS Feed Setup Guide](./opds-setup.md)

The short version:

1. Enable OPDS in Calibre-Web: **Admin** → **Edit Basic Configuration** → **Feature Configuration** → check **Enable OPDS feed**
2. Add the OPDS catalog in your reading app:
   - **URL:** `https://books.yourdomain.com/opds` (remote) or `http://localhost:8083/opds` (local)
   - **Credentials:** your Calibre-Web username and password
3. Browse and download books directly inside the app

The [OPDS guide](./opds-setup.md) covers app-specific setup for KOReader, Moon+ Reader, FBReader, and Panels.

## 4. Audiobooks with Audiobookshelf

Audiobookshelf has dedicated mobile apps with features like progress sync, offline downloads, sleep timer, and playback speed control.

1. Install the app:
   - **iOS:** Search "Audiobookshelf" in the App Store
   - **Android:** Search "Audiobookshelf" in Google Play
2. Open the app and enter your server address:
   - **Home network:** `http://localhost:13378`
   - **Remote:** `https://audiobooks.yourdomain.com` (via Cloudflare Tunnel)
3. Log in with your Audiobookshelf credentials
4. Browse your library, download books for offline listening, and your progress syncs automatically

> **Tip:** Audiobookshelf can also serve ebooks alongside audiobooks. If you add the ebooks folder as a library (Media Type: Books), you can browse ebooks from the same app. See [Step 9](./09-books-stack.md) for library configuration.

## 5. Remote Access

All methods above work from outside your home network using either Cloudflare Tunnel or Tailscale.

### Cloudflare Tunnel (recommended for simplicity)

No app install needed on your phone — just use HTTPS URLs:

| Service | Remote URL |
|---------|-----------|
| Calibre-Web | `https://books.yourdomain.com` |
| Audiobookshelf | `https://audiobooks.yourdomain.com` |
| OPDS feed | `https://books.yourdomain.com/opds` |

Replace `yourdomain.com` with the domain you configured in your Cloudflare Tunnel.

### Tailscale (for private network access)

Install [Tailscale](https://tailscale.com) on your phone and your server ([Step 2](./02-tailscale.md)). Then use the server's Tailscale IP:

| Service | Tailscale URL |
|---------|--------------|
| Calibre-Web | `http://100.x.y.z:8083` |
| Audiobookshelf | `http://100.x.y.z:13378` |
| OPDS feed | `http://100.x.y.z:8083/opds` |

Replace `100.x.y.z` with your server's Tailscale IP (find it with `tailscale ip -4` on the server).

> **When to use which:** Cloudflare Tunnel is easier (no app on your phone) and gives you HTTPS. Tailscale is better when you want to access all services by IP without setting up individual hostnames.

## Choosing a Method

| Scenario | Recommended Method |
|----------|-------------------|
| "I just want to read a chapter quickly" | Browser reader |
| "I read a lot and want the best experience" | OPDS + dedicated reader app |
| "I'm going on a flight with no internet" | Download to device beforehand |
| "I listen to audiobooks on my commute" | Audiobookshelf app |
| "I have an e-ink Kindle or Kobo" | OPDS via KOReader, or Send to Kindle |

## Troubleshooting

### Can't connect remotely

- **Cloudflare Tunnel:** Verify the tunnel is running: `docker logs cloudflared`
- **Tailscale:** Ensure Tailscale is running on both your phone and server: `tailscale status`
- **Both:** Confirm Calibre-Web is running: `docker ps | grep calibre-web`

### Downloaded book won't open

- Check the format — most mobile readers handle EPUB best
- Use Calibre-Web's **Convert** button to get an EPUB version
- If the file is DRM-protected, it won't open in third-party readers

### Browser reader shows blank page

- Try a different browser (Safari and Chrome both work)
- Clear browser cache and reload
- Some very large PDFs may struggle — download and use a PDF reader instead

### Reading progress not syncing

- **Calibre-Web browser reader:** Progress is per-user. Make sure you're logged into the same account on each device
- **Audiobookshelf:** Progress syncs automatically when connected. If offline, it syncs when you reconnect
- **OPDS downloads:** No sync — books are standalone files on your device. Use OPDS for download, not progress tracking

## Related Guides

- [Step 9: Books Stack](./09-books-stack.md) — Calibre-Web, Audiobookshelf, and Readarr setup
- [OPDS Feed Setup](./opds-setup.md) — Detailed OPDS configuration and app-by-app instructions
- [Kindle Email Delivery](./kindle-email-setup.md) — Send books directly to your Kindle (Issue #112)
