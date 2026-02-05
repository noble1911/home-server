# Step 5: Install OrbStack

OrbStack is a fast, lightweight Docker runtime optimized for Apple Silicon Macs.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/05-orbstack.sh | bash
```

## Manual

### Install OrbStack

```bash
brew install --cask orbstack
```

### Start OrbStack

```bash
open -a OrbStack
```

### Verify Installation

```bash
docker --version
# Should show: Docker version 24.x.x or later

docker info
# Should show OrbStack as the context
```

## What This Does

- Installs OrbStack (includes Docker CLI and daemon)
- Provides a lightweight alternative to Docker Desktop
- Optimized for Apple Silicon with lower memory usage
- Includes Docker Compose built-in

## Why OrbStack?

| Feature | OrbStack | Docker Desktop |
|---------|----------|----------------|
| Memory usage | ~500MB idle | ~2GB idle |
| Startup time | ~1 second | ~10 seconds |
| Apple Silicon | Native | Native |
| Free for personal | Yes | Yes |

## Troubleshooting

**Docker command not found:**
```bash
# OrbStack adds docker to PATH automatically
# If not working, restart your terminal or run:
source ~/.zprofile
```

**OrbStack not starting:**
```bash
# Check if OrbStack is running
pgrep -x OrbStack

# Start manually
open -a OrbStack
```

## Next Step

→ [Step 6: Configure External Drive](./06-external-drive.md)
