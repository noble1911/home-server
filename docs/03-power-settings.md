# Step 3: Configure Power Settings

Keep the Mac Mini running 24/7 as a server.

## Automated

```bash
curl -fsSL https://raw.githubusercontent.com/noble1911/home-server/main/scripts/03-power-settings.sh | bash
```

## Manual

### Option A: Via System Settings (GUI)

1. Open **System Settings** → **Energy**
2. Enable **"Prevent automatic sleeping when display is off"**
3. Enable **"Wake for network access"**
4. Enable **"Start up automatically after a power failure"**

### Option B: Via Terminal

```bash
# Prevent sleep
sudo pmset -a sleep 0
sudo pmset -a disksleep 0

# Wake on network access (Wake-on-LAN)
sudo pmset -a womp 1

# Auto-restart after power failure
sudo pmset -a autorestart 1
```

### Verify Settings

```bash
pmset -g
```

You should see:
```
 sleep           0
 disksleep       0
 womp            1
 autorestart     1
```

## What This Does

| Setting | Purpose |
|---------|---------|
| `sleep 0` | Never sleep the system |
| `disksleep 0` | Never spin down the hard drive |
| `womp 1` | Wake when network packet received (Wake-on-LAN) |
| `autorestart 1` | Automatically boot after power outage |

## Troubleshooting

**Mac keeps sleeping:**
```bash
# Check what's preventing/allowing sleep
pmset -g assertions
```

**Need to temporarily allow sleep:**
```bash
# Re-enable sleep (set to minutes, e.g., 30)
sudo pmset -a sleep 30
```

## Next Step

→ [Step 4: SSH Setup](./04-ssh.md) *(optional - skip if managing Mac Mini directly)*

Or continue to:
→ [Step 5: Install OrbStack](./05-orbstack.md)
