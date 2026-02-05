# Step 2: Install Tailscale

Tailscale provides secure access to your server from anywhere without exposing ports to the internet.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/02-tailscale.sh | bash
```

## Manual

### Install via Homebrew

```bash
brew install --cask tailscale
```

### Launch and Sign In

```bash
open -a Tailscale
```

1. Click the Tailscale icon in the menu bar
2. Sign in with your account (Google, Microsoft, GitHub, etc.)
3. Approve the device

### Verify Connection

```bash
tailscale status
# Should show your device and any others on your tailnet

tailscale ip -4
# Shows your Tailscale IP (100.x.y.z)
```

## What This Does

- Installs Tailscale VPN client
- Creates a secure mesh network between your devices
- Provides a stable IP (100.x.y.z) that works from anywhere
- No port forwarding or firewall configuration needed

## Accessing Your Server Remotely

Once Tailscale is running on both machines:

```bash
# From your MacBook (also running Tailscale)
ssh ron@mac-mini           # Uses Tailscale MagicDNS
ssh ron@100.x.y.z          # Uses Tailscale IP
```

## Next Step

→ [Step 3: Power Settings](./03-power-settings.md)
