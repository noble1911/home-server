# Google OAuth Setup

This guide walks you through creating Google OAuth credentials so Butler can access Google Calendar and Gmail on behalf of household members.

**Time:** ~10 minutes, one-time setup.

---

## 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown at the top and select **New Project**
3. Name it something like `Butler Home Server`
4. Click **Create**

## 2. Enable Google APIs

1. In your new project, go to **APIs & Services > Library**
2. Search for **Google Calendar API**, click it and press **Enable**
3. Go back to the Library, search for **Gmail API**, click it and press **Enable**

## 3. Configure the OAuth Consent Screen

1. Go to **APIs & Services > OAuth consent screen**
2. Choose **External** user type (Internal is only for Google Workspace orgs)
3. Fill in the required fields:
   - **App name:** `Butler`
   - **User support email:** your email
   - **Developer contact:** your email
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes** and add:
   - `https://www.googleapis.com/auth/calendar.readonly`
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/userinfo.email`
6. Click **Save and Continue**
7. On the **Test users** page, add the Google accounts of your household members
8. Click **Save and Continue**

## 4. Create OAuth 2.0 Credentials

1. Go to **Clients** (in the left sidebar under your project)
2. Click **Create OAuth client ID**
3. Choose **Web application** as the application type
4. Name it `Butler Web`
5. Under **Authorized redirect URIs**, add:
   - `http://localhost:8000/api/oauth/google/callback` (for local development)
   - `https://YOUR-TUNNEL-DOMAIN/api/oauth/google/callback` (for production)
6. Click **Create**
7. Copy the **Client ID** and **Client Secret**

## 5. Configure Butler

Add the credentials to your `butler/.env` file:

```bash
GOOGLE_CLIENT_ID=123456789-abcdef.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your-secret-here
```

The redirect URI is derived automatically from how you access the PWA (LAN, localhost, or Cloudflare Tunnel), so `GOOGLE_REDIRECT_URI` and `OAUTH_FRONTEND_URL` don't need to be set. The defaults work as fallbacks if needed.

## 6. Restart Butler

```bash
docker compose restart butler-api
```

Each household member can now connect their Google account (Calendar + Gmail) in **Settings > Connected Services**.

---

## Notes

### Testing vs Production Mode

Your OAuth app starts in **Testing** mode. This is fine for a home server:

- **Testing mode:** Up to 100 test users (more than enough for a household). Users must be added to the test users list in step 3.7 above.
- **Unverified app warning:** Users will see a "Google hasn't verified this app" screen. Click **Advanced > Go to Butler (unsafe)** to proceed. This is normal for self-hosted apps.
- **Production mode:** Requires Google's app review process. Not needed for personal use.

### Adding More Google Services

The same OAuth credentials work for additional Google APIs. To add a new service:

1. Enable the API in Google Cloud Console (APIs & Services > Library)
2. Add the required scope to the consent screen (APIs & Services > OAuth consent screen > Scopes)
3. Add the scope to `GOOGLE_SCOPES` in `butler/api/oauth.py`
4. Existing users will need to disconnect and reconnect to grant the new scope
