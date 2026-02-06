# Step 15: Configure Alexa Integration (haaska)

Connect Amazon Alexa to Home Assistant using haaska — a free, open-source Smart Home skill adapter that runs on AWS Lambda.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/15-alexa-haaska.sh | bash
```

> The script checks prerequisites, downloads haaska, and generates a config template.
> Most of this setup is manual (AWS Console + Amazon Developer Console).

## Manual

### Prerequisites

Before starting, ensure:

| Requirement | How to verify |
|-------------|---------------|
| Home Assistant running | Open http://localhost:8123 |
| Cloudflare Tunnel running | `docker logs cloudflared` shows "Connection registered" |
| HA accessible via tunnel URL | Open `https://ha.yourdomain.com` in a browser |
| HA Long-Lived Access Token | See [Step 11](./11-smart-home.md#generate-long-lived-access-token) |

You'll also need:
- An **Amazon account** (the one linked to your Echo devices)
- A **credit card** for AWS signup (you won't be charged — Lambda free tier covers 1M requests/month)

### Architecture

```
"Alexa, turn on the lights"
         │
         ▼
┌─────────────────┐
│   Amazon Echo    │
└────────┬────────┘
         │ Alexa Smart Home API
         ▼
┌─────────────────┐
│   AWS Lambda     │  ← haaska translates Alexa → HA API calls
│   (haaska)       │
│   FREE TIER      │
└────────┬────────┘
         │ HTTPS
         ▼
┌─────────────────┐
│  Cloudflare      │  ← Encrypted tunnel, no open ports on Mac Mini
│  Tunnel          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Home Assistant   │  ← Controls your smart devices
│ :8123            │
└─────────────────┘
```

---

### 1. Create AWS Account

1. Go to https://aws.amazon.com and click **Create an AWS Account**
2. Use the **same email** as your Amazon/Alexa account (simplifies linking)
3. Select **Personal** account type
4. Add a payment method (required but you won't be charged)
5. Select the **Basic Support - Free** plan

**Set a billing alarm** (recommended):
1. AWS Console → **Billing** → **Budgets**
2. Create budget → **Zero spend budget**
3. Enter your email for alerts

### 2. Create IAM Role for Lambda

The Lambda function needs permissions to write logs.

1. Go to **AWS Console → IAM → Roles**
2. Click **Create role**
3. Select **AWS service** → **Lambda**
4. Search for and attach: `AWSLambdaBasicExecutionRole`
5. Name: `lambda_basic_execution`
6. Click **Create role**

### 3. Register Login with Amazon (LWA)

haaska uses Login with Amazon for Alexa account linking (how Amazon verifies your identity).

1. Go to https://developer.amazon.com/loginwithamazon/console/site/lwa/overview.html
2. Click **Create a New Security Profile**
3. Fill in:
   - **Security Profile Name:** `Home Assistant`
   - **Security Profile Description:** `haaska Alexa skill for Home Assistant`
   - **Consent Privacy Notice URL:** `https://www.example.com/privacy` (placeholder is fine)
4. Click **Save**
5. Hover over the new profile → click the **gear icon** (Show Client ID and Client Secret)
6. **Copy and save** the **Client ID** and **Client Secret** — you'll need these later

> ⚠️ Don't close this tab — you'll return here to add redirect URLs in a later step.

### 4. Create Alexa Smart Home Skill

1. Go to https://developer.amazon.com/alexa/console/ask
2. Click **Create Skill**
3. Configure:
   - **Skill name:** `Home Assistant` (or your preference)
   - **Default language:** English (UK)
   - **Skill model:** Choose **Smart Home**
   - **Hosting method:** **Provision your own**
4. Click **Create Skill**
5. **Copy the Skill ID** (shown at the top, starts with `amzn1.ask.skill.`)  — you'll need this for Lambda

### 5. Download and Prepare haaska

On your Mac Mini (or wherever you're working):

```bash
# Download latest haaska release
mkdir -p /tmp/haaska && cd /tmp/haaska
curl -L -o haaska.zip https://github.com/mike-grant/haaska/releases/download/1.1.0/haaska_1.1.0.zip
```

Alternatively, build from source (recommended if the pre-built ZIP has issues with newer Lambda runtimes):

```bash
git clone https://github.com/mike-grant/haaska.git /tmp/haaska-src
cd /tmp/haaska-src
make
# Produces haaska.zip in the current directory
```

Create the configuration file:

```bash
cat > /tmp/haaska/config.json << 'EOF'
{
    "url": "https://ha.yourdomain.com",
    "bearer_token": "YOUR_LONG_LIVED_ACCESS_TOKEN",
    "ssl_verify": true,
    "debug": false
}
EOF
```

Replace:
- `https://ha.yourdomain.com` → your Cloudflare Tunnel URL for Home Assistant
- `YOUR_LONG_LIVED_ACCESS_TOKEN` → the token from [Step 11](./11-smart-home.md#generate-long-lived-access-token)

> **Using Cloudflare Tunnel means you skip** the port forwarding, DuckDNS, and SSL certificate steps that the haaska wiki describes. The tunnel provides HTTPS and routing automatically.

### 6. Create Lambda Function

**Important:** Select the correct AWS region for your Alexa language:

| Alexa Language | AWS Region |
|----------------|------------|
| English (UK) | **EU (Ireland)** `eu-west-1` |
| English (US) | US East (N. Virginia) `us-east-1` |
| English (AU) | US West (Oregon) `us-west-2` |
| German / French / Italian / Spanish | EU (Ireland) `eu-west-1` |
| Japanese | Asia Pacific (Tokyo) `ap-northeast-1` |

> For a UK-based setup, make sure you're in **eu-west-1** before creating the function.

1. Go to **AWS Console → Lambda** (ensure correct region in top-right)
2. Click **Create function**
3. Select **Author from scratch**
4. Configure:
   - **Function name:** `haaska`
   - **Runtime:** Python 3.12 (or latest available)
   - **Architecture:** x86_64
   - **Execution role:** Use existing role → `lambda_basic_execution`
5. Click **Create function**

#### Upload haaska code

1. In your new function → **Code** tab
2. Click **Upload from** → **.zip file**
3. Upload the `haaska.zip` you downloaded/built
4. Click **Save**

#### Add config.json

You have two options:

**Option A — Bundle before upload (simpler):**
1. Unzip `haaska.zip` to a folder
2. Copy your `config.json` into that folder
3. Re-zip everything together
4. Upload the combined ZIP to Lambda

**Option B — Use Lambda's code editor (after upload):**
1. After uploading `haaska.zip`, look at the **Code source** panel
2. Click **File** → **New File**
3. Name it `config.json`
4. Paste your config content
5. Click **Deploy**

#### Configure handler and timeout

1. Go to **Configuration** tab → **General configuration** → **Edit**
2. Set:
   - **Handler:** `haaska.event_handler`
   - **Timeout:** `30` seconds (increase from default 3s)
   - **Memory:** `128` MB (sufficient)
3. Click **Save**

#### Add Alexa Smart Home trigger

1. Click **+ Add trigger**
2. Select **Alexa Smart Home**
3. Paste your **Skill ID** from Step 4
4. Click **Add**
5. **Copy the Lambda function ARN** (top-right of the page) — you'll need this next

### 7. Link Lambda to Alexa Skill

Go back to the Alexa Developer Console (https://developer.amazon.com/alexa/console/ask):

1. Open your **Home Assistant** skill
2. Go to **Smart Home** in the left sidebar
3. Under **Default endpoint**, paste your **Lambda function ARN**
4. Click **Save**

#### Configure Account Linking

1. In the Alexa skill console, go to **Account Linking** (left sidebar)
2. Enable **Do you allow users to create an account or link to an existing account?**
3. Fill in:
   - **Authorization URI:** `https://www.amazon.com/ap/oa`
   - **Access Token URI:** `https://api.amazon.com/auth/o2/token`
   - **Client ID:** (from Login with Amazon in Step 3)
   - **Client Secret:** (from Login with Amazon in Step 3)
   - **Scope:** Add `profile`
   - **Authorization Grant Type:** Auth Code Grant
4. **Copy all the Redirect URLs** shown on this page (typically 3-4 URLs)
5. Click **Save**

#### Add Redirect URLs to Login with Amazon

1. Go back to https://developer.amazon.com/loginwithamazon/console/site/lwa/overview.html
2. Click the **gear icon** next to your **Home Assistant** security profile
3. Go to **Web Settings**
4. Under **Allowed Return URLs**, add **each redirect URL** you copied from the Alexa Account Linking page
5. Click **Save**

### 8. Enable Skill and Link Account

1. Open the **Alexa app** on your phone
2. Go to **More** → **Skills & Games** → **Your Skills** → **Dev**
3. Find **Home Assistant** → tap **Enable**
4. You'll be prompted to **Link Account** — sign in with your Amazon credentials
5. You should see "Successfully linked"

### 9. Discover Devices

1. In the Alexa app: **Devices** → **+** → **Add Device**
2. Tap **Other** → **Discover Devices**
3. Or say: **"Alexa, discover my devices"**
4. Wait 20-30 seconds — your exposed HA entities should appear

> If no devices appear, see [Troubleshooting](#troubleshooting) below.

---

## Expose Entities in Home Assistant

Only entities explicitly exposed in HA will appear in Alexa.

### Via UI (recommended)

1. In HA: **Settings → Voice assistants → Expose**
2. Toggle on each entity you want Alexa to control
3. Optionally set friendly names (Alexa uses these for voice commands)

### Via configuration.yaml

```yaml
alexa:
  smart_home:
    filter:
      include_domains:
        - light
        - switch
        - climate
        - cover
        - fan
        - lock
      include_entities:
        - media_player.living_room
```

After changing exposed entities, re-run device discovery in the Alexa app.

---

## Voice Command Examples

| Command | What Happens |
|---------|--------------|
| "Alexa, turn on the lights" | Turns on all lights |
| "Alexa, turn off bedroom light" | Turns off specific light |
| "Alexa, set living room to 50%" | Dims living room to 50% |
| "Alexa, set thermostat to 20" | Sets heating to 20°C |
| "Alexa, lock the front door" | Locks a smart lock |
| "Alexa, what's the temperature inside?" | Reads a temperature sensor |
| "Alexa, is the front door locked?" | Reports lock state |

---

## Troubleshooting

### No devices discovered

1. **Check entities are exposed** in HA: Settings → Voice assistants → Expose
2. **Verify the token** in `config.json` is correct and not expired
3. **Check tunnel URL** is accessible: open it in a browser, confirm HA loads
4. **Check Lambda logs**: AWS Console → CloudWatch → Log groups → `/aws/lambda/haaska`
5. **Re-run discovery**: "Alexa, discover my devices"

### "Server is unresponsive" error

This usually means Lambda can't reach Home Assistant:

1. Verify Cloudflare Tunnel is running: `docker logs cloudflared`
2. Test the URL from Lambda's perspective — the tunnel URL must be publicly reachable via HTTPS
3. Ensure `ssl_verify` is `true` in config.json (Cloudflare provides valid certs)
4. Check Lambda timeout is set to 30 seconds (not the default 3s)

### Account linking fails

1. Verify **all** redirect URLs from Alexa Console are added to Login with Amazon
2. Ensure Client ID and Client Secret match between Alexa skill and LWA
3. Try disabling and re-enabling the skill in the Alexa app

### Lambda errors / Python runtime issues

The pre-built haaska 1.1.0 ZIP was built for Python 3.6. If you see import errors:

1. Check CloudWatch logs for the specific error
2. Build from source instead:
   ```bash
   git clone https://github.com/mike-grant/haaska.git
   cd haaska && make
   ```
3. Re-upload the newly built `haaska.zip`
4. Ensure the runtime in Lambda matches what you built for

### Devices found but commands fail

1. Check the entity type is supported (lights, switches, climate, covers, locks, fans)
2. Verify the entity is working in HA first (test from the HA dashboard)
3. Check CloudWatch logs for error details

---

## Security Notes

- ✅ **No public ports** opened on your Mac Mini
- ✅ **Cloudflare Tunnel** provides encrypted HTTPS access
- ✅ **Long-Lived Access Token** authenticates Lambda → HA
- ✅ **Account Linking** authenticates you → Alexa → Lambda
- ⚠️ **Keep your HA token secure** — don't commit `config.json` to git
- ⚠️ **Set an AWS billing alarm** — Lambda free tier is generous but be safe

---

## Cost Summary

| Component | Monthly Cost |
|-----------|-------------|
| haaska (open source) | Free |
| AWS Lambda (1M requests/month free) | Free |
| Cloudflare Tunnel (free tier) | Free |
| **Total** | **£0.00** |

Compare: Home Assistant Cloud (Nabu Casa) costs £5/month for the same Alexa integration.

---

## Next Step

→ Congratulations! Your home server stack is fully configured.

See [HOMESERVER_PLAN.md](../HOMESERVER_PLAN.md) for the full architecture overview.
