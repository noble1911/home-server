# Step 10: Deploy Photos & Files Stack

Deploy Immich (photo management with AI) and Nextcloud (file sync).

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/10-photos-files.sh | bash
```

## Manual

### 1. Start Services

```bash
cd docker/photos-files-stack
docker compose up -d
```

### 2. Verify Running

```bash
docker compose ps
# Should show: immich-server, immich-machine-learning, immich-redis, immich-postgres, nextcloud
```

## Services

| Service | URL | Purpose |
|---------|-----|---------|
| Immich | http://localhost:2283 | Photo backup & management |
| Nextcloud | http://localhost:8080 | File sync & collaboration |
| PostgreSQL | localhost:5432 | Shared database |

## Initial Configuration

### Immich

1. Open http://localhost:2283
2. Click "Getting Started" and create admin account
3. **Install mobile apps:**
   - iOS: App Store "Immich"
   - Android: Google Play "Immich"
4. **Configure mobile app:**
   - Server URL: `http://your-mac-mini-ip:2283` (or Cloudflare Tunnel URL)
   - Login with admin account
   - Settings > Backup > Enable automatic backup
5. **Web features:**
   - Face recognition (automatic)
   - Albums and sharing
   - Map view (if photos have GPS)
   - Search by content (ML-powered)

### Nextcloud

1. Open http://localhost:8080
2. Create admin account
3. **Database configuration:**
   - Choose PostgreSQL
   - Host: `immich-postgres`
   - Database: `nextcloud`
   - User: `postgres`
   - Password: `postgres`
4. **Install clients:**
   - Desktop: https://nextcloud.com/install/#install-clients
   - Mobile: App stores
5. **Configure sync:**
   - Choose folders to sync
   - Set up selective sync if needed

## Shared PostgreSQL

This stack includes PostgreSQL with vector extensions (for Immich's ML features). The same database will be used for:

| Database/Schema | Purpose |
|-----------------|---------|
| `immich` | Immich photo metadata |
| `nextcloud` | Nextcloud file metadata |
| `butler.*` | Butler AI memory (auto-initialized) |

**Butler schema tables:**
| Table | Purpose |
|-------|---------|
| `butler.users` | User profiles and soul/personality config |
| `butler.user_facts` | Things Butler learns about users |
| `butler.conversation_history` | Conversation context for continuity |
| `butler.scheduled_tasks` | Reminders and automations |

The Butler schema is automatically initialized when this script runs. It's idempotent (safe to run multiple times).

**Connection details:**
- Host: `localhost:5432` (from Mac) or `immich-postgres:5432` (from containers)
- User: `postgres`
- Password: `postgres`

> ⚠️ **Security Note:** Change the default password for production use!

## Volume Mappings

| Service | Container Path | Host Path |
|---------|----------------|-----------|
| Immich | `/usr/src/app/upload` | `/Volumes/HomeServer/Photos/Immich` |
| Nextcloud | `/var/www/html/data` | `/Volumes/HomeServer/Documents/Nextcloud` |
| PostgreSQL | `/var/lib/postgresql/data` | Docker volume (SSD) |
| Immich ML | `/cache` | Docker volume (SSD) |

## Mobile Backup Setup

### Immich (Photos)

Best practices for photo backup:

1. **Enable auto-backup** in app settings
2. **Background app refresh** must be enabled
3. **Battery optimization** should be disabled for the app
4. **WiFi-only upload** to save mobile data
5. **Original quality** preserves full resolution

### Nextcloud (Files)

For document sync:

1. **Auto-upload** specific folders (e.g., Documents)
2. **Instant upload** for camera (if not using Immich)
3. **Offline files** for important documents

## Face Recognition

Immich automatically:
- Detects faces in photos
- Clusters similar faces
- Allows you to name people
- Searches by person name

Initial processing takes time. Check progress:
```bash
docker logs immich-machine-learning
```

## Remote Access

For access outside your home:

1. **Via Cloudflare Tunnel (recommended):**
   - Use your tunnel URL (e.g., `https://photos.yourdomain.com`)
   - Works from anywhere with no client software needed

2. **Direct IP (LAN only):**
   - Find Mac IP: `ipconfig getifaddr en0`
   - Use: `http://192.168.x.x:2283`

## Docker Commands

```bash
# View logs
docker logs immich-server
docker logs nextcloud

# Check ML processing
docker logs immich-machine-learning

# Restart all
cd docker/photos-files-stack
docker compose restart

# Update images
docker compose pull
docker compose up -d
```

## Troubleshooting

### Immich upload failing

Check Immich server logs:
```bash
docker logs immich-server
```

Common issues:
- Disk space on external drive
- Permissions on Photos folder

### Nextcloud "Access through untrusted domain"

If you see this error when accessing Nextcloud via Cloudflare Tunnel (e.g. `files.yourdomain.com`), add your domain to trusted_domains:

```bash
docker exec -u www-data nextcloud php occ config:system:set trusted_domains 5 --value="files.yourdomain.com"
docker exec -u www-data nextcloud php occ config:system:set overwriteprotocol --value="https"
docker exec -u www-data nextcloud php occ config:system:set overwrite.cli.url --value="https://files.yourdomain.com"
```

Or set `TUNNEL_DOMAIN=yourdomain.com` (or `NEXTCLOUD_TRUSTED_DOMAIN=files.yourdomain.com`) before re-running `scripts/10-photos-files.sh` to configure this automatically.

### Nextcloud performance

For large file counts:
```bash
# Enter container
docker exec -it nextcloud bash

# Run maintenance
php occ files:scan --all
php occ maintenance:repair
```

### PostgreSQL connection issues

```bash
# Test connection
docker exec immich-postgres psql -U postgres -c "SELECT 1"

# Check logs
docker logs immich-postgres
```

### Butler schema issues

```bash
# Verify Butler schema exists
docker exec immich-postgres psql -U postgres -d immich -c "\dn butler"

# List Butler tables
docker exec immich-postgres psql -U postgres -d immich -c "\dt butler.*"

# Re-run initialization (safe, idempotent)
./scripts/init-butler-schema.sh

# Check default user exists
docker exec immich-postgres psql -U postgres -d immich -c "SELECT * FROM butler.users;"
```

## Backup Considerations

⚠️ **Photos are irreplaceable!** Consider:

1. **Local backup** to Mac SSD (automatic via script)
2. **Optional cloud backup:**
   - iCloud 2TB (£6.99/mo)
   - Google One 2TB (£7.99/mo)
   - Backblaze B2 (pay per GB)

See HOMESERVER_PLAN.md for backup strategy details.

## Next Step

→ [Step 11: Deploy Smart Home](./11-smart-home.md)
