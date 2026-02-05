# Step 6: Configure External Drive

Set up the external drive with the correct directory structure for all services.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/06-external-drive.sh | bash
```

**With a different drive name:**
```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/06-external-drive.sh | bash -s -- --drive-name=MyDrive
```

## Manual

### 1. Format the Drive (if new)

Open **Disk Utility** and format the external drive:

- **Name:** `HomeServer` (or your preferred name)
- **Format:** APFS (recommended) or Mac OS Extended (Journaled)
- **Scheme:** GUID Partition Map

### 2. Create Directory Structure

```bash
DRIVE="/Volumes/HomeServer"

# Media
mkdir -p "$DRIVE/Media/Movies/4K"
mkdir -p "$DRIVE/Media/Movies/HD"
mkdir -p "$DRIVE/Media/TV/4K"
mkdir -p "$DRIVE/Media/TV/HD"
mkdir -p "$DRIVE/Media/Music"

# Books
mkdir -p "$DRIVE/Books/eBooks/Calibre Library"
mkdir -p "$DRIVE/Books/Audiobooks"

# Photos
mkdir -p "$DRIVE/Photos/Immich/library"
mkdir -p "$DRIVE/Photos/Immich/upload"
mkdir -p "$DRIVE/Photos/Immich/thumbs"

# Documents
mkdir -p "$DRIVE/Documents/Nextcloud"

# Downloads
mkdir -p "$DRIVE/Downloads/Complete/Movies"
mkdir -p "$DRIVE/Downloads/Complete/TV"
mkdir -p "$DRIVE/Downloads/Complete/Books"
mkdir -p "$DRIVE/Downloads/Incomplete"

# Backups
mkdir -p "$DRIVE/Backups/Databases/immich"
mkdir -p "$DRIVE/Backups/Databases/jellyfin"
mkdir -p "$DRIVE/Backups/Databases/homeassistant"
mkdir -p "$DRIVE/Backups/Databases/arr-stack"
mkdir -p "$DRIVE/Backups/Configs"
```

### 3. Verify Structure

```bash
tree -L 2 /Volumes/HomeServer
```

## Directory Layout

```
/Volumes/HomeServer/
├── Media/              # 5TB - Movies, TV, Music
│   ├── Movies/
│   │   ├── 4K/
│   │   └── HD/
│   ├── TV/
│   │   ├── 4K/
│   │   └── HD/
│   └── Music/
├── Books/              # 350GB - eBooks and Audiobooks
│   ├── eBooks/
│   └── Audiobooks/
├── Photos/             # 1TB - Immich photo library
│   └── Immich/
├── Documents/          # 200GB - Nextcloud files
│   └── Nextcloud/
├── Downloads/          # 400GB - Download buffer
│   ├── Complete/
│   └── Incomplete/
└── Backups/            # 200GB - Database backups
    ├── Databases/
    └── Configs/
```

## Troubleshooting

### Drive Disconnects on Sleep

Prevent Mac from sleeping (already configured in step 3), or:

```bash
# Install Amphetamine from App Store to keep Mac awake
# Or use caffeinate for temporary prevention:
caffeinate -d &
```

### Drive Not Mounting Automatically

1. Open **System Preferences > Users & Groups**
2. Select your user > **Login Items**
3. The drive should auto-mount when connected

### Wrong Drive Name

If your drive has a different name:
```bash
# List available drives
ls /Volumes/

# Run script with your drive name
DRIVE_NAME=YourDriveName ./scripts/06-external-drive.sh
```

## What This Does

- Creates the full directory structure for all services
- Organizes media by type and quality (4K vs HD)
- Separates downloads from completed media
- Sets up backup directories for databases

## Next Step

→ [Step 7: Deploy Download Stack](./07-download-stack.md)
