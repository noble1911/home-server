# Step 11: Deploy Smart Home Stack

Deploy Home Assistant and Cloudflare Tunnel for Alexa integration.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/11-smart-home.sh | bash
```

## Manual

### 1. Start Home Assistant

```bash
cd docker/smart-home-stack
docker compose up -d homeassistant
```

### 2. Verify Running

```bash
docker compose ps
```

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| Home Assistant | http://localhost:8123 | Smart home hub |
| Cloudflare Tunnel | - | Secure external access for Alexa |

## Initial Configuration

### Home Assistant

1. Open http://localhost:8123
2. Create admin account
3. Set location, timezone, units
4. **Add integrations** for your devices:
   - Settings > Devices & Services > Add Integration
   - Common: Hue, LIFX, TP-Link, Sonos, etc.

### Generate Long-Lived Access Token

Required for haaska (Alexa integration):

1. Click your profile (bottom left)
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Name it "haaska"
5. **Copy and save the token** (shown only once!)

## Cloudflare Tunnel Setup

The tunnel allows Alexa (via AWS Lambda) to reach Home Assistant without exposing your IP.

### 1. Create Cloudflare Account

1. Go to https://dash.cloudflare.com
2. Sign up for free account
3. You don't need a domain for tunnels

### 2. Create Tunnel

1. In Cloudflare dashboard: **Zero Trust > Networks > Tunnels**
2. Click "Create a tunnel"
3. Name: `home-assistant`
4. Copy the tunnel token

### 3. Start Cloudflared

```bash
export CLOUDFLARE_TUNNEL_TOKEN='your-token-here'
cd docker/smart-home-stack
docker compose up -d cloudflared
```

### 4. Configure Tunnel Route

In Cloudflare dashboard:
1. Click your tunnel > "Configure"
2. Add a public hostname:
   - Subdomain: `ha` (or your choice)
   - Domain: Select your domain (or use a `cfargotunnel.com` free subdomain)
   - Service: `http://homeassistant:8123`

Your HA will be accessible at: `https://ha.yourdomain.com`

## Alexa Integration (haaska)

haaska is a free bridge between Alexa and Home Assistant.

### Architecture

```
"Alexa, turn on living room"
         ↓
    Amazon Echo
         ↓
    AWS Lambda (haaska)
         ↓
    Cloudflare Tunnel
         ↓
    Home Assistant
         ↓
    Your smart devices
```

### 1. Create AWS Account

1. Go to https://aws.amazon.com
2. Create free account
3. AWS Lambda has a generous free tier (1M requests/month)

### 2. Deploy haaska

Follow the official guide: https://github.com/mike-grant/haaska

Quick steps:
1. Download haaska release
2. Edit `config.json`:
   ```json
   {
     "url": "https://your-tunnel-url.com",
     "bearer_token": "your-long-lived-access-token",
     "ssl_verify": true
   }
   ```
3. Deploy to Lambda via CloudFormation

### 3. Create Alexa Skill

1. Go to https://developer.amazon.com/alexa/console/ask
2. Create new skill (Smart Home type)
3. Link to your Lambda function
4. Enable skill in Alexa app

### 4. Discover Devices

1. Open Alexa app
2. Devices > + > Add Device
3. Other > Discover Devices
4. Your HA devices appear!

## Home Assistant Configuration

### Exposing Entities to Alexa

In Home Assistant, only entities in your "Exposed" list work with Alexa.

1. Settings > Voice assistants > Expose
2. Select entities to expose
3. Or use `configuration.yaml`:

```yaml
# Expose specific domains
alexa:
  smart_home:
    filter:
      include_domains:
        - light
        - switch
        - climate
        - cover
```

### Example Automations

```yaml
# Morning routine
automation:
  - alias: "Good Morning"
    trigger:
      - platform: time
        at: "07:00:00"
    condition:
      - condition: state
        entity_id: person.ron
        state: "home"
    action:
      - service: light.turn_on
        target:
          entity_id: light.bedroom
        data:
          brightness_pct: 50

# Coming home
  - alias: "Welcome Home"
    trigger:
      - platform: state
        entity_id: person.ron
        to: "home"
    action:
      - service: light.turn_on
        target:
          entity_id: light.hallway
```

## Voice Commands

After setup, you can say:

| Command | What Happens |
|---------|--------------|
| "Alexa, turn on the lights" | Turns on all lights |
| "Alexa, set bedroom to 50%" | Dims bedroom lights |
| "Alexa, set thermostat to 20" | Adjusts heating |
| "Alexa, lock the front door" | Locks smart lock |
| "Alexa, what's the temperature inside?" | Reads sensor |

## Docker Commands

```bash
# View logs
docker logs homeassistant
docker logs cloudflared

# Restart
cd docker/smart-home-stack
docker compose restart

# Update
docker compose pull
docker compose up -d
```

## Troubleshooting

### Alexa can't discover devices

1. Check token is correct in haaska config
2. Verify tunnel is running: `docker logs cloudflared`
3. Test tunnel URL in browser
4. Check entities are exposed in HA

### Cloudflared not connecting

```bash
# Check logs
docker logs cloudflared

# Verify token is set
echo $CLOUDFLARE_TUNNEL_TOKEN
```

### Home Assistant slow

- Check logs: `docker logs homeassistant`
- Database may need cleanup: Settings > System > Purge

## Security Notes

- ✅ Cloudflare Tunnel = no open ports
- ✅ HTTPS encryption end-to-end
- ✅ Token-based authentication
- ⚠️ Keep tokens secure (don't commit to git!)

## Next Step

→ [Step 12: Deploy Voice Stack](./12-voice-stack.md)
