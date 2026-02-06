# Step 4: SSH Setup (Optional)

> **Skip this step** if you'll manage the Mac Mini directly with a keyboard and monitor attached.

SSH lets you manage the Mac Mini from another computer without physical access.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/04-ssh.sh | bash
```

## Manual

### Enable SSH on Mac Mini

**Via System Settings:**
1. Open **System Settings** → **General** → **Sharing**
2. Enable **"Remote Login"**

**Via Terminal:**
```bash
sudo systemsetup -setremotelogin on
```

Verify:
```bash
sudo systemsetup -getremotelogin
# Should show: Remote Login: On
```

### Find Your Mac Mini's Address

```bash
# Local IP
ipconfig getifaddr en0    # Wi-Fi
ipconfig getifaddr en1    # Ethernet

# Hostname
echo "$(hostname).local"
```

### Prepare SSH Directory

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

## Connecting from Another Machine

### Basic Connection

```bash
ssh yourusername@mac-mini.local
# or
ssh yourusername@192.168.1.xxx
```

### Set Up Key Authentication (Recommended)

On your **MacBook** (or other client machine):

```bash
# Generate a key (if you don't have one)
ssh-keygen -t ed25519 -C "macbook-to-macmini"
# Save to: ~/.ssh/id_ed25519_macmini

# Copy to Mac Mini
ssh-copy-id -i ~/.ssh/id_ed25519_macmini.pub ron@mac-mini.local
```

### Add SSH Config for Easy Access

Add to `~/.ssh/config` on your MacBook:

```ssh-config
Host macmini
  HostName mac-mini.local    # Use LAN hostname or IP
  User ron
  IdentityFile ~/.ssh/id_ed25519_macmini
  IdentitiesOnly yes
  ServerAliveInterval 60
```

Now just run:
```bash
ssh macmini
```

---

## Useful Commands

```bash
# Copy files to Mac Mini
scp ./docker-compose.yml macmini:~/home-server/

# Copy files from Mac Mini
scp macmini:~/home-server/config.yml ./

# Sync directories
rsync -avz --progress ./configs/ macmini:~/home-server/configs/

# Port forward (access Jellyfin on localhost:8096)
ssh -L 8096:localhost:8096 macmini

# Multiple port forwards
ssh -L 8096:localhost:8096 -L 8123:localhost:8123 macmini
```

---

## Troubleshooting

**"Connection refused"**
- SSH not enabled: `sudo systemsetup -setremotelogin on`
- Firewall blocking port 22

**"Host key verification failed"**
```bash
ssh-keygen -R mac-mini.local
```

**"Permission denied (publickey)"**
```bash
# Check key was copied
ssh ron@mac-mini.local "cat ~/.ssh/authorized_keys"

# Fix permissions on Mac Mini
ssh ron@mac-mini.local "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

**Can't find Mac Mini on network**
```bash
# Discover via Bonjour
dns-sd -B _ssh._tcp

# Scan local network
nmap -sn 192.168.1.0/24
```

---

## Security Hardening (Optional)

After confirming key authentication works, disable password login:

```bash
# On Mac Mini
sudo sed -i '' 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

# Restart SSH
sudo launchctl unload /System/Library/LaunchDaemons/ssh.plist
sudo launchctl load /System/Library/LaunchDaemons/ssh.plist
```

## Next Step

→ [Step 5: Install OrbStack](./05-orbstack.md)
