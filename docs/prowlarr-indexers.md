# Prowlarr Indexer Setup Guide

Configure indexers in Prowlarr so Radarr, Sonarr, and Readarr can search for content.

> **Prerequisites:** Prowlarr is running ([Step 7](./07-download-stack.md)) and you've completed initial authentication setup at http://localhost:9696.

## How Prowlarr Works

Prowlarr is an indexer manager. Instead of adding indexers to each *arr app individually, you add them once in Prowlarr and it syncs them everywhere:

```
                    ┌─── Radarr  (movies)
Prowlarr ───────────┼─── Sonarr  (tv)
(indexers live here) └─── Readarr (books/audiobooks)
```

When you search in Radarr for a movie, Radarr asks Prowlarr, which queries all your indexers and returns results.

## 1. Add Public Indexers

Public indexers don't require an account — they're the easiest way to get started.

1. Open http://localhost:9696
2. Go to **Indexers > Add Indexer** (+ button)
3. Search for one of the recommended public indexers below
4. Click the indexer name, review the defaults, then click **Test** and **Save**

### Recommended Public Indexers

| Indexer | Content | Notes |
|---------|---------|-------|
| 1337x | Movies, TV, Books | Large general-purpose tracker |
| RARBG (rarbg.to clone mirrors) | Movies, TV | Popular for well-tagged releases |
| The Pirate Bay | Movies, TV, Books | Widely known, variable quality |
| Nyaa | Anime | Best source for anime content |
| Library Genesis (LibGen) | Books | Large ebook/academic library |

> **Tip:** Start with 2-3 public indexers. You can always add more later. Quality over quantity — too many indexers slow down searches.

### Adding an Indexer Step-by-Step

1. **Indexers** tab → click **+** (Add Indexer)
2. In the search box, type the indexer name (e.g. "1337x")
3. Click the indexer entry
4. **Base URL:** Usually auto-filled. If the default doesn't work, try an alternative URL from the dropdown
5. **Categories:** Leave defaults or customize (see [Category Mapping](#5-category-mapping) below)
6. Click **Test** — you should see a green checkmark
7. Click **Save**

## 2. Add Private Trackers

Private trackers require an account and usually provide better quality, speed, and retention. Authentication varies by tracker.

### API Key Authentication

Most private trackers use an API key (sometimes called a passkey).

1. **Indexers** → **+** (Add Indexer)
2. Search for your tracker name
3. Fill in the **API Key** or **Passkey** from your tracker's profile page
4. Click **Test** and **Save**

Where to find your API key:
- Log into the tracker website
- Go to your **Profile** or **Settings** page
- Look for "API Key", "Passkey", or "RSS Key"

### Cookie Authentication

Some trackers (especially older ones) use cookie-based auth instead of API keys.

1. Log into the tracker in your browser
2. Open DevTools (F12) → **Application** tab → **Cookies**
3. Copy the cookie string (or specific cookies the indexer config asks for)
4. In Prowlarr, paste the cookie value into the **Cookie** field
5. Click **Test** and **Save**

> **Note:** Cookies expire. If a cookie-authenticated indexer stops working, you'll need to log in again and update the cookie.

### User/Password Authentication

A few indexers accept direct username/password login:

1. Enter your tracker **Username** and **Password** in the indexer config
2. Click **Test** and **Save**

## 3. Connect Prowlarr to *arr Apps

This tells Prowlarr where to sync your indexers. You only need to do this once.

1. Go to **Settings > Apps**
2. Click **+** (Add Application) for each app:

### Radarr (Movies)

| Field | Value |
|-------|-------|
| Prowlarr Server | `http://prowlarr:9696` |
| Radarr Server | `http://radarr:7878` |
| API Key | Copy from Radarr > Settings > General |
| Sync Level | Full Sync |

### Sonarr (TV)

| Field | Value |
|-------|-------|
| Prowlarr Server | `http://prowlarr:9696` |
| Sonarr Server | `http://sonarr:8989` |
| API Key | Copy from Sonarr > Settings > General |
| Sync Level | Full Sync |

### Readarr (Books & Audiobooks)

| Field | Value |
|-------|-------|
| Prowlarr Server | `http://prowlarr:9696` |
| Readarr Server | `http://readarr:8787` |
| API Key | Copy from Readarr > Settings > General |
| Sync Level | Full Sync |

> **Sync Level explained:** "Full Sync" means Prowlarr pushes all compatible indexers to the app and keeps them in sync. "Add and Remove Only" syncs indexers but doesn't update settings. Use Full Sync unless you have a specific reason not to.

After adding all apps, click **Sync App Indexers** (the refresh icon) to trigger an immediate sync.

## 4. Verify the Setup

### Test Search in Prowlarr

1. Go to **Search** tab
2. Enter a search term (e.g. a well-known movie title)
3. Select a search type (Movie, TV, Book, etc.)
4. Click **Search**
5. You should see results from your indexers

### Verify Indexers Synced to Apps

1. Open Radarr → **Settings > Indexers**
   - You should see your indexers listed with "(Prowlarr)" suffix
2. Open Sonarr → **Settings > Indexers**
   - Same indexers should appear
3. Open Readarr → **Settings > Indexers**
   - Book-compatible indexers should appear

### Test Search in an *arr App

1. Open Radarr → **Add New** → search for a movie
2. Results should come back from your Prowlarr indexers
3. Repeat for Sonarr (TV show) and Readarr (book)

## 5. Category Mapping

Prowlarr maps indexer categories to *arr app categories. This controls which indexers serve which apps. Correct mapping prevents book indexers from cluttering movie searches and vice versa.

### Default Categories

| *arr App | Prowlarr Categories |
|----------|---------------------|
| Radarr | Movies (2000-2999) |
| Sonarr | TV (5000-5999) |
| Readarr - Books | Books (7000-7999), specifically Books/Ebook (7020) |
| Readarr - Audiobooks | Audio/Audiobook (3030) |

### Customizing Categories

If an indexer uses non-standard categories:

1. Open the indexer in Prowlarr
2. Scroll to **Category Mappings** section
3. Map the indexer's custom categories to standard Newznab categories

For example, if a tracker calls ebooks "E-Library" instead of using standard numbering:
- Map "E-Library" → Books/Ebook (7020)

### Anime Category Tip

For anime, you may want both Radarr and Sonarr to receive anime results:
- Movies/Anime (2060) → Radarr picks these up
- TV/Anime (5070) → Sonarr picks these up

## Troubleshooting

### Indexer test fails with "Unable to connect"

- Check the indexer's base URL — try an alternative URL from the dropdown
- Some indexers are region-blocked; you may need a VPN on the host
- Verify Prowlarr has internet access: check `docker logs prowlarr` for connection errors

### Indexer returns no results

- Some indexers have rate limits — wait a minute and try again
- Check if the indexer requires a minimum search length
- Try searching for a very popular/well-known title first
- Verify the indexer is enabled (green toggle in the indexer list)

### Indexers not appearing in Radarr/Sonarr/Readarr

- Check **Settings > Apps** — is the app connection green?
- Click the **Sync App Indexers** button (refresh icon)
- Verify API keys are correct (copy them fresh from each app)
- Check category mappings — the indexer may not have categories matching the app
- Look at `docker logs prowlarr` for sync errors

### "API Key is invalid" when adding an app

- API keys are per-app. Copy from the specific app's **Settings > General** page
- Make sure you're using the **API Key**, not a different token
- Use Docker hostnames (`radarr`, `sonarr`) not `localhost` for server URLs

### Cookie-auth indexer stopped working

- Log into the tracker website in your browser
- Copy fresh cookies using DevTools
- Update the cookie in the indexer settings
- Click **Test** to verify

### Search is slow

- Too many indexers slow down every search. Disable or remove indexers you don't actually use
- Check **System > Tasks** for any stuck tasks
- Under **Indexers**, review response times — consistently slow indexers can be removed

## Next Steps

- [Step 7: Download Stack](./07-download-stack.md) — qBittorrent + Prowlarr deployment
- [Step 8: Media Stack](./08-media-stack.md) — Radarr, Sonarr, Jellyfin setup
- [Step 9: Books Stack](./09-books-stack.md) — Audiobookshelf, LazyLibrarian setup
