# Step 1: Install Homebrew

Homebrew is the package manager for macOS - you'll need it for most tools.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/01-homebrew.sh | bash
```

## Manual

### Install Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Add to PATH (Apple Silicon Macs)

After installation, add Homebrew to your shell:

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### Verify Installation

```bash
brew --version
# Should show: Homebrew 4.x.x
```

## What This Does

- Installs Homebrew to `/opt/homebrew` (Apple Silicon) or `/usr/local` (Intel)
- Adds `brew` command to your PATH
- Enables installing packages with `brew install <package>`

## Next Step

→ [Step 3: Power Settings](./03-power-settings.md)
