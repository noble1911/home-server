# Home Server

Self-hosted media server with AI voice assistant on Mac Mini M4.

See [HOMESERVER_PLAN.md](./HOMESERVER_PLAN.md) for the complete architecture and implementation plan.

---

## Remote Setup Guide

This guide explains how to configure and manage the Mac Mini remotely from your MacBook Pro (or any other machine).

### Prerequisites

- Mac Mini M4 connected to your home network (ethernet recommended)
- MacBook Pro (or any SSH client machine)
- Both machines on the same network initially for setup

---

## Step 1: Enable SSH on Mac Mini

On the **Mac Mini** (requires physical access or screen sharing for initial setup):

1. **Open System Settings** → **General** → **Sharing**

2. **Enable "Remote Login"** (this enables the SSH server)

3. **Note the connection info** displayed, e.g.:
   ```
   ssh ron@192.168.1.100
   ```
   Or using the hostname:
   ```
   ssh ron@mac-mini.local
   ```

4. **Optional but recommended:** Click "Info" (ⓘ) next to Remote Login to configure:
   - "Allow access for: Only these users" → Add your user
   - This restricts SSH to specific accounts

### Finding the Mac Mini's IP Address

On the Mac Mini, run:
```bash
# Get local IP address
ipconfig getifaddr en0    # Wi-Fi
ipconfig getifaddr en1    # Ethernet (try both)

# Or see all network interfaces
ifconfig | grep "inet " | grep -v 127.0.0.1
```

Or check **System Settings** → **Network** → Select your connection → See IP address.

---

## Step 2: Set Up SSH Key Authentication (Recommended)

Password authentication works but key-based auth is more secure and convenient.

### On your MacBook Pro:

```bash
# Generate a new SSH key (if you don't have one)
ssh-keygen -t ed25519 -C "macbook-to-macmini"

# When prompted:
# - Save to: ~/.ssh/id_ed25519_macmini (or default)
# - Passphrase: recommended for security

# Copy your public key to the Mac Mini
ssh-copy-id -i ~/.ssh/id_ed25519_macmini.pub ron@mac-mini.local

# Or manually (if ssh-copy-id isn't available):
cat ~/.ssh/id_ed25519_macmini.pub | ssh ron@mac-mini.local "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

### Add SSH Config Entry

Add to `~/.ssh/config` on your MacBook:

```ssh-config
# Home Server - Mac Mini M4
Host macmini
  HostName mac-mini.local          # Or use IP: 192.168.1.100
  User ron
  IdentityFile ~/.ssh/id_ed25519_macmini
  IdentitiesOnly yes

  # Optional: Keep connection alive
  ServerAliveInterval 60
  ServerAliveCountMax 3
```

Now you can simply run:
```bash
ssh macmini
```

---

## Step 3: Test the Connection

```bash
# Basic connection test
ssh macmini "echo 'Connected to Mac Mini!' && hostname && uname -a"

# Check system info
ssh macmini "system_profiler SPHardwareDataType | grep -E 'Model|Chip|Memory'"
```

---

## Step 4: Remote Access Outside Home Network

### Option A: Tailscale (Recommended)

Tailscale creates a secure mesh VPN - no port forwarding needed.

**On Mac Mini:**
1. Download from https://tailscale.com/download/mac
2. Install and sign in
3. Note the Tailscale IP (e.g., `100.x.y.z`) or MagicDNS name

**On MacBook:**
1. Install Tailscale
2. Sign in with same account
3. Connect via Tailscale hostname:
   ```bash
   ssh ron@mac-mini  # MagicDNS name
   # or
   ssh ron@100.x.y.z  # Tailscale IP
   ```

**Update your SSH config:**
```ssh-config
Host macmini
  HostName mac-mini              # Tailscale MagicDNS name
  User ron
  IdentityFile ~/.ssh/id_ed25519_macmini
  IdentitiesOnly yes
```

### Option B: Port Forwarding (Not Recommended)

Exposing SSH (port 22) to the internet is risky. If you must:
- Change SSH to a non-standard port
- Use fail2ban or similar
- Require key-only authentication
- Consider a VPN instead

---

## Step 5: Keep Mac Mini Awake

The Mac Mini should stay awake for SSH access and server duties.

**On Mac Mini:**

1. **System Settings** → **Energy**
   - Enable "Prevent automatic sleeping when display is off"
   - Enable "Wake for network access"

2. **Or via Terminal:**
   ```bash
   # Prevent sleep entirely (run on Mac Mini)
   sudo pmset -a sleep 0
   sudo pmset -a disksleep 0

   # Enable wake on network
   sudo pmset -a womp 1

   # Verify settings
   pmset -g
   ```

---

## Step 6: Useful Remote Commands

Once SSH is set up, here are commands you'll use frequently:

```bash
# Copy files to Mac Mini
scp ./docker-compose.yml macmini:~/homeserver/

# Copy files from Mac Mini
scp macmini:~/homeserver/config.yml ./

# Sync entire directory (rsync is better for large transfers)
rsync -avz --progress ./configs/ macmini:~/homeserver/configs/

# Run interactive shell
ssh macmini

# Run single command
ssh macmini "docker ps"

# Port forward (access Mac Mini's port 8096 on localhost:8096)
ssh -L 8096:localhost:8096 macmini

# Multiple port forwards
ssh -L 8096:localhost:8096 -L 8123:localhost:8123 macmini
```

---

## Troubleshooting

### "Connection refused"
- SSH not enabled on Mac Mini
- Firewall blocking port 22
- Wrong IP address

```bash
# Check if SSH is running on Mac Mini
sudo launchctl list | grep ssh
# Should show: com.openssh.sshd
```

### "Host key verification failed"
The Mac Mini's host key changed (reinstall, new machine, etc.):
```bash
ssh-keygen -R mac-mini.local
ssh-keygen -R 192.168.1.100  # if using IP
```

### "Permission denied (publickey)"
Key not copied correctly:
```bash
# Verify key is on Mac Mini
ssh ron@mac-mini.local "cat ~/.ssh/authorized_keys"

# Check permissions on Mac Mini
ssh ron@mac-mini.local "ls -la ~/.ssh"
# Should be: drwx------ for .ssh, -rw------- for authorized_keys
```

### Can't find Mac Mini on network
```bash
# Discover devices using Bonjour
dns-sd -B _ssh._tcp

# Or scan local network (requires nmap)
nmap -sn 192.168.1.0/24
```

---

## Security Checklist

- [ ] SSH key authentication enabled
- [ ] Password authentication disabled (optional, more secure)
- [ ] Firewall enabled on Mac Mini
- [ ] Tailscale for remote access (not port forwarding)
- [ ] Regular macOS updates
- [ ] Strong user account password (for local access)

### Disable Password Authentication (Optional)

After confirming key auth works:

```bash
# On Mac Mini, edit SSH config
sudo nano /etc/ssh/sshd_config

# Add or modify:
PasswordAuthentication no
ChallengeResponseAuthentication no

# Restart SSH
sudo launchctl unload /System/Library/LaunchDaemons/ssh.plist
sudo launchctl load /System/Library/LaunchDaemons/ssh.plist
```

---

## Next Steps

Once SSH is configured:

1. [x] Clone this repo on Mac Mini: `git clone git@github.com:noble1911/home-server.git`
2. [ ] Install OrbStack
3. [ ] Install Homebrew
4. [ ] Follow [HOMESERVER_PLAN.md](./HOMESERVER_PLAN.md) Phase 1
