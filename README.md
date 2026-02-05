# Home Server

Self-hosted media server with AI voice assistant on Mac Mini M4.

See [HOMESERVER_PLAN.md](./HOMESERVER_PLAN.md) for the complete architecture and implementation plan.

---

## Quick Start

On your Mac Mini, open Terminal and run:

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/bootstrap.sh | bash
```

This will:
- ✅ Install Homebrew (package manager)
- ✅ Install Tailscale (secure remote access)
- ✅ Configure Mac to stay awake 24/7
- ✅ Enable SSH for remote management

**Skip SSH** if you'll manage the Mac Mini directly (keyboard + monitor):

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/bootstrap.sh | bash -s -- --no-ssh
```

Or follow the [manual setup](#manual-setup) instructions below.

---

## Manual Setup

### Step 1: Install Homebrew

Homebrew is the package manager for macOS - you'll need it for most tools.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

After installation, add to your PATH (Apple Silicon Macs):

```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### Step 2: Install Tailscale

Tailscale provides secure access to your server from anywhere (phone, laptop, etc.) without exposing ports to the internet.

```bash
brew install --cask tailscale
open -a Tailscale
```

Sign in with your Tailscale account (or create one - free tier is plenty).

### Step 3: Configure Power Settings

Keep the Mac Mini running 24/7:

**Via System Settings:**
1. **System Settings** → **Energy**
2. Enable "Prevent automatic sleeping when display is off"
3. Enable "Wake for network access"

**Or via Terminal:**

```bash
# Prevent sleep
sudo pmset -a sleep 0
sudo pmset -a disksleep 0

# Wake on network access
sudo pmset -a womp 1

# Auto-restart after power failure
sudo pmset -a autorestart 1

# Verify settings
pmset -g
```

### Step 4: Clone This Repository

```bash
git clone https://github.com/noble1911/home-server.git
cd home-server
```

Now follow [HOMESERVER_PLAN.md](./HOMESERVER_PLAN.md) to continue setup.

---

## Optional: Remote Management via SSH

> **Skip this section** if you prefer to manage the Mac Mini directly (keyboard + monitor attached).

SSH lets you manage the Mac Mini from another computer (e.g., your MacBook) without needing physical access.

### Enable SSH on Mac Mini

**Via System Settings:**
1. **System Settings** → **General** → **Sharing**
2. Enable **"Remote Login"**

**Or via Terminal:**

```bash
sudo systemsetup -setremotelogin on
```

Verify it's enabled:
```bash
sudo systemsetup -getremotelogin
# Should show: Remote Login: On
```

### Find Your Mac Mini's Address

```bash
# Get local IP
ipconfig getifaddr en0    # Wi-Fi
ipconfig getifaddr en1    # Ethernet

# Or use hostname
echo "$(hostname).local"
```

### Connect from Another Machine

From your MacBook (or any SSH client):

```bash
ssh yourusername@mac-mini.local
# or
ssh yourusername@192.168.1.xxx
```

### Set Up SSH Key Authentication (Recommended)

Keys are more secure and convenient than passwords.

**On your MacBook:**

```bash
# Generate a key (if you don't have one)
ssh-keygen -t ed25519 -C "macbook-to-macmini"
# Save to: ~/.ssh/id_ed25519_macmini

# Copy to Mac Mini
ssh-copy-id -i ~/.ssh/id_ed25519_macmini.pub ron@mac-mini.local
```

**Add SSH config for easy access** (`~/.ssh/config` on MacBook):

```ssh-config
Host macmini
  HostName mac-mini.local    # Or Tailscale IP: 100.x.y.z
  User ron
  IdentityFile ~/.ssh/id_ed25519_macmini
  IdentitiesOnly yes
  ServerAliveInterval 60
```

Now just run:
```bash
ssh macmini
```

### Useful Remote Commands

```bash
# Copy files to Mac Mini
scp ./docker-compose.yml macmini:~/home-server/

# Copy files from Mac Mini
scp macmini:~/home-server/config.yml ./

# Sync directories
rsync -avz --progress ./configs/ macmini:~/home-server/configs/

# Port forward (access Mac Mini's Jellyfin on localhost:8096)
ssh -L 8096:localhost:8096 macmini
```

### Troubleshooting SSH

**"Connection refused"**
- SSH not enabled: `sudo systemsetup -setremotelogin on`
- Check firewall isn't blocking port 22

**"Host key verification failed"**
```bash
ssh-keygen -R mac-mini.local
```

**"Permission denied (publickey)"**
```bash
# Check key was copied correctly
ssh ron@mac-mini.local "cat ~/.ssh/authorized_keys"

# Fix permissions on Mac Mini
ssh ron@mac-mini.local "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

**Can't find Mac Mini on network**
```bash
# Discover via Bonjour
dns-sd -B _ssh._tcp

# Scan local network (requires nmap)
nmap -sn 192.168.1.0/24
```

---

## Security Checklist

- [ ] Tailscale installed and signed in
- [ ] Strong user account password
- [ ] Regular macOS updates enabled
- [ ] (If using SSH) Key authentication set up
- [ ] (If using SSH) Consider disabling password auth:
  ```bash
  # On Mac Mini - only after confirming key auth works!
  sudo sed -i '' 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
  sudo launchctl unload /System/Library/LaunchDaemons/ssh.plist
  sudo launchctl load /System/Library/LaunchDaemons/ssh.plist
  ```

---

## Next Steps

1. [ ] Complete setup above
2. [ ] Install OrbStack: `brew install --cask orbstack`
3. [ ] Follow [HOMESERVER_PLAN.md](./HOMESERVER_PLAN.md) Phase 1
