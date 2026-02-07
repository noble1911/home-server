# Kindle Email Delivery Setup Guide

Configure Calibre-Web to send ebooks directly to your Kindle with one click — no cable or manual transfer needed.

> **Prerequisites:** Calibre-Web is running ([Step 9](./09-books-stack.md)) with initial setup complete, a Gmail account, and an Amazon account with a Kindle device or Kindle app.

## What is Send to Kindle?

Every Kindle device and Kindle app has a unique email address (e.g. `yourname@kindle.com`). When you email an ebook to that address from an approved sender, Amazon delivers it wirelessly to your device. Calibre-Web integrates this natively — click "Send to Kindle" on any book's detail page and it arrives on your Kindle within minutes.

This requires two things:
1. **SMTP configured in Calibre-Web** — so it can send emails via your Gmail
2. **Your Gmail whitelisted in Amazon** — so Amazon accepts the email

## 1. Find Your Kindle Email Address

1. Go to [Amazon Manage Your Content and Devices](https://www.amazon.co.uk/hz/mycd/myx#/home/settings/payment) (or `.com` for US)
2. Click the **Preferences** tab
3. Scroll down to **Personal Document Settings**
4. Under **Send-to-Kindle Email**, find the address for your device

| Device | Typical Address |
|--------|----------------|
| Kindle e-reader | `yourname@kindle.com` |
| Kindle iPad/iPhone app | `yourname_XXXX@kindle.com` |
| Kindle Android app | `yourname_YYYY@kindle.com` |

> **Tip:** Each device has a separate email address. Pick the one you read on most — you can always add more later.

## 2. Add Your Gmail to Amazon's Approved List

Amazon only accepts emails from approved senders. On the same **Personal Document Settings** page:

1. Scroll to **Approved Personal Document E-mail List**
2. Click **Add a new approved e-mail address**
3. Enter the Gmail address you'll use for Calibre-Web SMTP (e.g. `you@gmail.com`)
4. Click **Add Address**

> **Important:** The address must match exactly what Calibre-Web sends from. If you use `yourname@gmail.com` here, use the same in the SMTP config below.

## 3. Create a Gmail App Password

Gmail requires an App Password for SMTP access — your regular Google password won't work.

1. Go to [myaccount.google.com](https://myaccount.google.com)
2. Navigate to **Security**
3. Under **Signing in to Google**, enable **2-Step Verification** (required for App Passwords)
4. Once 2-Step Verification is active, go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
5. Enter a name (e.g. "Calibre-Web") and click **Create**
6. Copy the **16-character password** that appears (spaces don't matter)

> **Keep this password safe** — you'll need it in the next step. Google only shows it once.

## 4. Configure SMTP in Calibre-Web

### Option A: Manual (Web UI)

1. Open http://localhost:8083
2. Log in as admin
3. Go to **Admin** → **Edit Basic Configuration** → **Email Server (SMTP)**
4. Enter these settings:

| Field | Value |
|-------|-------|
| SMTP hostname | `smtp.gmail.com` |
| SMTP port | `587` |
| Encryption | `STARTTLS` |
| SMTP login | Your Gmail address |
| SMTP password | The 16-character App Password from step 3 |
| From e-mail | Your Gmail address |

5. Click **Save**
6. Click **Test** (next to Save) to send a test email — check your inbox

### Option B: Automated (Setup Script)

If you add SMTP credentials to `~/.homeserver-credentials` **before** running `scripts/09-books-stack.sh`, the setup script configures SMTP automatically.

Add these lines to `~/.homeserver-credentials`:

```bash
# Calibre-Web SMTP (for Kindle email delivery)
CALIBRE_SMTP_SERVER=smtp.gmail.com
CALIBRE_SMTP_PORT=587
CALIBRE_SMTP_ENCRYPTION=1
CALIBRE_SMTP_LOGIN=you@gmail.com
CALIBRE_SMTP_PASSWORD=xxxx-xxxx-xxxx-xxxx
CALIBRE_SMTP_FROM=you@gmail.com
```

Then run (or re-run) the books stack setup:

```bash
./scripts/09-books-stack.sh
```

The script writes these into Calibre-Web's database on first run. If SMTP is already configured, it skips this step.

## 5. Set Your Kindle Email in Your Profile

Each household member does this with their own Calibre-Web account:

1. Log in to Calibre-Web at http://localhost:8083
2. Click your **username** (top-right) → **Profile**
3. In the **Kindle E-mail Address** field, enter your `@kindle.com` address from step 1
4. Click **Save**

## 6. Test the Workflow

1. Open any book in Calibre-Web
2. Click the **Send to Kindle** button on the book detail page
3. Wait a few minutes — the book should appear on your Kindle

| What to Check | Expected Result |
|---------------|-----------------|
| "Send to Kindle" button visible | Yes, on every book detail page |
| Test email from SMTP config | Arrives in your Gmail inbox |
| Book delivery to Kindle | Appears in your Kindle library within 5 minutes (on Wi-Fi) |

## 7. Supported Formats

| Format | What Happens | Notes |
|--------|-------------|-------|
| EPUB | Auto-converted by Amazon | Best quality — Amazon converts to Kindle-native format |
| MOBI | Sent directly | Legacy format, still works |
| AZW3 | Sent directly | Native Kindle format |
| PDF | Sent directly | Layout preserved, no text reflow on small screens |
| DOC / DOCX | Sent directly | Converted by Amazon on delivery |
| TXT | Sent directly | Basic formatting only |

> **Size limit:** Amazon accepts attachments up to **50 MB**. For larger files (comics, image-heavy PDFs), use [OPDS](./opds-setup.md) or direct download instead.

> **Format conversion:** The Docker Compose includes `DOCKER_MODS=linuxserver/mods:universal-calibre`, which lets Calibre-Web convert between formats server-side. If a book is only available in a format your Kindle doesn't handle well, convert it to EPUB first.

## Troubleshooting

### "Send to Kindle" button not visible

- Ensure SMTP is configured: **Admin** → **Edit Basic Configuration** → **Email Server (SMTP)**
- Ensure your user profile has a Kindle email address set

### Email sends but book never arrives on Kindle

- Check the sender email is in Amazon's Approved Personal Document E-mail List (exact match)
- Ensure your Kindle is connected to Wi-Fi
- Check [Manage Your Content and Devices](https://www.amazon.co.uk/hz/mycd/myx) for pending deliveries
- Allow up to 10 minutes for Amazon to convert and deliver

### SMTP authentication failed

- Must use a **Gmail App Password**, not your regular Google password
- Verify 2-Step Verification is enabled on your Google account
- Regenerate the App Password if it's been revoked
- Check SMTP settings: `smtp.gmail.com`, port `587`, encryption `STARTTLS`

### "File too large" error

- Amazon's limit is 50 MB per email
- For large PDFs or comics, use [OPDS](./opds-setup.md) or download directly from Calibre-Web
- Compress images using Calibre-Web's polish feature (if `universal-calibre` mod is installed)

### Book arrives but formatting is wrong

- **EPUB** gives the best results — Amazon converts it to Kindle-native format with proper text reflow
- **PDF** preserves layout but won't reflow text on small Kindle screens
- Convert to EPUB in Calibre-Web before sending for the best reading experience

## Next Steps

- [Step 9: Books Stack](./09-books-stack.md) — Full Calibre-Web setup and configuration
- [OPDS Feed Setup](./opds-setup.md) — Browse and download books from mobile reading apps
