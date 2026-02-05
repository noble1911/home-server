# Home Server

Self-hosted media server with AI voice assistant on Mac Mini M4.

## Quick Start

Run everything at once:

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash
```

Skip SSH if managing Mac Mini directly:

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/setup.sh | bash -s -- --no-ssh
```

---

## Setup Guide

| Step | Script | Manual | Description |
|------|--------|--------|-------------|
| 1 | [01-homebrew.sh](scripts/01-homebrew.sh) | [docs](docs/01-homebrew.md) | Install Homebrew package manager |
| 2 | [02-tailscale.sh](scripts/02-tailscale.sh) | [docs](docs/02-tailscale.md) | Install Tailscale for secure remote access |
| 3 | [03-power-settings.sh](scripts/03-power-settings.sh) | [docs](docs/03-power-settings.md) | Configure Mac to stay awake 24/7 |
| 4 | [04-ssh.sh](scripts/04-ssh.sh) | [docs](docs/04-ssh.md) | Enable SSH *(optional)* |
| 5 | *coming soon* | | Install OrbStack (Docker) |
| 6 | *coming soon* | | Deploy media stack |
| ... | | | |

Run individual steps:
```bash
# Example: just install Tailscale
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/02-tailscale.sh | bash
```

Or follow the manual docs for step-by-step instructions.

---

## Documentation

- **[HOMESERVER_PLAN.md](HOMESERVER_PLAN.md)** - Complete architecture and implementation plan
- **[TODO.md](TODO.md)** - Implementation progress tracker
- **[docs/](docs/)** - Step-by-step setup guides

---

## What Gets Installed

| Component | Purpose |
|-----------|---------|
| [Homebrew](https://brew.sh/) | Package manager for macOS |
| [Tailscale](https://tailscale.com/) | Secure mesh VPN for remote access |
| [OrbStack](https://orbstack.dev/) | Docker for macOS (coming soon) |
| [Jellyfin](https://jellyfin.org/) | Media streaming (coming soon) |
| ... | See [HOMESERVER_PLAN.md](HOMESERVER_PLAN.md) for full list |

---

## Repository Structure

```
home-server/
├── README.md                 # This file
├── HOMESERVER_PLAN.md        # Complete architecture plan
├── setup.sh                  # Run all setup steps
├── scripts/
│   ├── 01-homebrew.sh        # Individual step scripts
│   ├── 02-tailscale.sh
│   ├── 03-power-settings.sh
│   └── 04-ssh.sh
└── docs/
    ├── 01-homebrew.md        # Manual instructions for each step
    ├── 02-tailscale.md
    ├── 03-power-settings.md
    └── 04-ssh.md
```
