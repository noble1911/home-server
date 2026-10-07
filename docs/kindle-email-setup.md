# Send to Kindle

Ask Butler *"send Project Hail Mary to my Kindle"* and it finds the book in the
library (`Books/eBooks`), converts it to EPUB if needed, and emails it to your
Kindle from your own Gmail. The book appears in your Kindle library within a
few minutes.

> **Formats:** Amazon stopped accepting MOBI and AZW by email in late 2022 and
> accepts EPUB, so Butler sends EPUB (and PDF, DOCX, TXT as-is). MOBI, AZW3,
> FB2 and friends are converted to EPUB first by the `ebook-convert` container
> (Calibre). DRM-protected books can't be converted or sent.

## One-time setup (each person)

1. **Find your Kindle address.** On Amazon go to **Manage Your Content and
   Devices → Preferences → Personal Document Settings**. Each Kindle device and
   app has a *Send-to-Kindle E-Mail Address* like `yourname_123@kindle.com`.
2. **Approve your Gmail.** On the same page, under **Approved Personal Document
   E-mail List**, add the Gmail address you connected to Butler. Amazon silently
   drops email from anyone not on this list.
3. **Tell Butler.** In the Butler app go to **Settings → Account → Kindle
   address** and paste it in.
4. **Let Butler send from your Gmail.** In **Settings → Connected Services**,
   Google must be connected with sending allowed (*Email: … send*). If it says
   otherwise, tap **Reconnect**.

An admin can turn the feature off per person with the **Send to Kindle**
permission (Settings → Users). It's on by default.

## Using it

- *"Send Dune to my Kindle"*: Butler searches the library; if there are several
  matches it asks which one.
- *"What books do we have by Andy Weir?"*, then *"send the first one to my Kindle"*.
- Not in the library yet? Butler can download it with the books tool first.
- If Amazon rejected a book (you get an email from Amazon saying so), ask Butler
  to *"try sending it again and fix the EPUB"*: it re-processes the file through
  Calibre, which repairs most of the EPUBs Amazon dislikes.

Butler only ever sends to the Kindle address saved in **your** profile. There's
no way to make it email a book anywhere else, so it doesn't ask for approval.

## Limits

- **Size:** Gmail caps a message at 25 MB after encoding, which works out at
  about **18 MB** for the book. Bigger files (usually illustrated PDFs) need the
  [Send to Kindle app or website](https://www.amazon.com/sendtokindle).
- **Speed:** conversions take a few seconds to a minute; one runs at a time.

## How it works

```
Butler (send_to_kindle tool)
  ├─ finds the file under /mnt/external/Books/eBooks
  ├─ EPUB/PDF/DOCX/TXT ─────────────────────────────┐
  ├─ MOBI/AZW3/… ─ POST /convert ─▶ ebook-convert ──┤ (Calibre, read-only library)
  └─ Gmail API (user's own account) ─▶ you@kindle.com
```

- Tool: `butler/tools/kindle.py`. Converter: `butler/ebook_convert/` (built with
  butler-api from `butler/docker-compose.yml`; internal only, no host port).
- `EBOOK_CONVERT_TOKEN` in `butler/.env` is the shared secret between them.
- Kindle addresses live in `butler.users.kindle_email` (migration 016).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Butler says it was sent, but nothing arrives | Your Gmail isn't on Amazon's approved list (step 2), or the Kindle address is wrong |
| Amazon emails "We couldn't send…" | Ask Butler to resend with the EPUB fixed; if it still fails the file is probably damaged — try another copy |
| "No Kindle address is saved yet" | Settings → Account → Kindle address |
| "needs extra Google permission" | Settings → Connected Services → Reconnect next to Google |
| "the ebook converter isn't reachable" | On the server: `cd ~/home-server/butler && docker compose up -d ebook-convert` |
| "This book is DRM-protected" | It can't be converted; use a DRM-free copy |
