# OutClaw Dashboard — Cross-Platform Guide

## Supported Platforms

OutClaw Dashboard runs on:
- ✅ **Termux** (Android)
- ✅ **Windows** (PowerShell, CMD, Git Bash)
- ✅ **Linux** (Standard distributions)
- ✅ **Chromebook** (Crostini Linux container)
- ✅ **macOS**

## Platform-Specific Installation

### Termux (Android)

```bash
# 1. Install dependencies
pkg install python git

# 2. Clone or navigate to OutClaw
cd /path/to/OutClaw

# 3. Run installer
bash install_dashboard.sh

# 4. Optional: Enable storage access
termux-setup-storage

# 5. Optional: Install integrations
pkg install termux-api  # For file sharing
pkg install rclone      # For cloud sync
pkg install openssh     # For SSH
```

**Termux Notes:**
- Config directory: `$HOME/.outclaw`
- Test file location: `$HOME/outclaw_test.txt`
- Use `termux-share` for printing/sharing documents
- Camera can be used for scanning with `termux-camera-photo`

### Windows (PowerShell/CMD)

```powershell
# 1. Ensure Python 3.8+ installed
python --version

# 2. Navigate to OutClaw
cd C:\path\to\OutClaw

# 3. Run installer (Git Bash or PowerShell)
bash install_dashboard.sh
# Or manually:
pip install -r requirements-dashboard.txt

# 4. Run dashboard
python outclaw_dashboard.py
```

**Windows Notes:**
- Config directory: `%APPDATA%\OutClaw`
- Test file location: `%TEMP%\outclaw_test.txt`
- ANSI colors enabled automatically (Windows 10+)
- Use PowerShell for best compatibility

### Linux (Standard)

```bash
# 1. Install Python (if needed)
sudo apt install python3 python3-pip  # Debian/Ubuntu
sudo dnf install python3 python3-pip  # Fedora
sudo pacman -S python python-pip      # Arch

# 2. Navigate to OutClaw
cd /path/to/OutClaw

# 3. Run installer
bash install_dashboard.sh

# 4. Optional: Install integrations
sudo apt install rclone openssh-client  # Debian/Ubuntu
```

**Linux Notes:**
- Config directory: `~/.config/outclaw` or `~/.outclaw`
- Test file location: `/tmp/outclaw_test.txt`
- Full integration support (rclone, ssh, printing, scanning)

### Chromebook (Crostini)

```bash
# 1. Enable Linux (if not already)
# Settings → Advanced → Developers → Linux development environment

# 2. Install Python
sudo apt update
sudo apt install python3 python3-pip

# 3. Navigate to OutClaw
cd /path/to/OutClaw

# 4. Run installer
bash install_dashboard.sh
```

**Chromebook Notes:**
- Config directory: `~/.config/outclaw`
- Files limited to Linux container
- Access via Chrome OS file manager: "Linux files"
- Printing requires Chrome OS integration

## Setup Wizard

Run the interactive setup wizard for guided configuration:

```bash
python3 -m dashboard.setup_wizard
```

The wizard will:
1. Detect your platform automatically
2. Check for available integrations (rclone, ssh, etc.)
3. Configure LLM settings (optional)
4. Set up audit preferences
5. Configure external tools
6. Create personalized workflow timeline
7. Generate custom `config.yaml`

## External Integrations

### rclone (Cloud Sync)

**Installation:**
- Termux: `pkg install rclone`
- Windows: Download from https://rclone.org/downloads/
- Linux: `sudo apt install rclone` or download binary
- Chromebook: `sudo apt install rclone`

**Configuration:**
```bash
# Set up remote
rclone config

# Test sync
rclone sync ~/.outclaw remote:outclaw-backup
```

**Dashboard Integration:**
- Enable in setup wizard or config.yaml
- Set sync interval (default: 300 seconds)
- Auto-sync on audit completion (optional)

### SSH (Remote Access)

**Installation:**
- Termux: `pkg install openssh`
- Windows: Built-in (Windows 10+) or install OpenSSH
- Linux: `sudo apt install openssh-client`
- Chromebook: `sudo apt install openssh-client`

**Configuration:**
```bash
# Generate key (if needed)
ssh-keygen -t ed25519

# Test connection
ssh user@remote-host
```

**Dashboard Integration:**
- Configure default host in setup wizard
- Quick SSH shortcuts in dashboard
- Remote file access (future feature)

### Printing

**Platform Support:**

| Platform | Command | Notes |
|----------|---------|-------|
| Termux | `termux-share` | Shares to Android print dialog |
| Windows | `notepad /p` | Uses default printer |
| Linux | `lp` or `lpr` | CUPS printing system |
| Chromebook | `lp` | Chrome OS integration |

**Configuration:**
```yaml
# config.yaml
integrations:
  printing:
    enabled: true
    command: lp  # or platform-specific
```

### Scanning

**Platform Support:**

| Platform | Command | Notes |
|----------|---------|-------|
| Termux | `termux-camera-photo` | Uses device camera |
| Windows | Platform-specific | Requires scanner software |
| Linux | `scanimage` | SANE scanner support |
| Chromebook | `scanimage` | If scanner connected |

**Configuration:**
```yaml
# config.yaml
integrations:
  scanning:
    enabled: true
    command: scanimage
    output_format: pdf
```

### Image Viewing

**Platform Support:**

| Platform | Command | Notes |
|----------|---------|-------|
| Termux | `termux-open` | Opens in Android viewer |
| Windows | `start` | Default image viewer |
| Linux | `xdg-open` | Desktop environment default |
| Chromebook | `xdg-open` | Chrome OS viewer |

## Configuration Locations

### Config Directory

| Platform | Location |
|----------|----------|
| Termux | `$HOME/.outclaw` |
| Windows | `%APPDATA%\OutClaw` |
| Linux | `~/.config/outclaw` |
| Chromebook | `~/.config/outclaw` |

### Config File

All platforms use: `config.yaml` in config directory

### Log Files

- Main log: `<config_dir>/outclaw.log`
- Discoveries: `<config_dir>/discoveries.jsonl`
- Sync log: `<config_dir>/sync.log` (if rclone enabled)

## Platform-Specific Features

### Termux Exclusive

- **Storage Access**: `termux-setup-storage` for SD card access
- **File Sharing**: `termux-share` for Android share dialog
- **Camera Scanning**: `termux-camera-photo` for document capture
- **Notifications**: `termux-notification` for audit alerts

### Windows Exclusive

- **PowerShell Integration**: Native PowerShell command support
- **Windows Defender**: Automatic security scanning
- **Registry Integration**: (Future) Windows registry settings

### Linux/Chromebook Exclusive

- **CUPS Printing**: Full printer management
- **SANE Scanning**: Professional scanner support
- **Desktop Integration**: Native file manager integration

## Troubleshooting

### Termux Issues

**Problem**: `pkg install python` fails  
**Solution**: Update repositories first:
```bash
pkg update && pkg upgrade
```

**Problem**: Storage permission denied  
**Solution**: Run `termux-setup-storage` and grant permission

**Problem**: Dashboard colors not working  
**Solution**: Install `ncurses-utils`:
```bash
pkg install ncurses-utils
```

### Windows Issues

**Problem**: ANSI colors not working  
**Solution**: Use PowerShell or Windows Terminal (not CMD)

**Problem**: `bash` command not found  
**Solution**: Install Git Bash or use PowerShell:
```powershell
pip install -r requirements-dashboard.txt
python outclaw_dashboard.py
```

**Problem**: Path errors with backslashes  
**Solution**: Use forward slashes or raw strings:
```python
path = r"C:\Users\Name\Documents\file.txt"
# or
path = "C:/Users/Name/Documents/file.txt"
```

### Linux/Chromebook Issues

**Problem**: Permission denied on install  
**Solution**: Don't use `sudo` for pip:
```bash
pip3 install --user -r requirements-dashboard.txt
```

**Problem**: `python3` not found  
**Solution**: Install Python:
```bash
sudo apt update
sudo apt install python3 python3-pip
```

**Problem**: Dashboard crashes on startup  
**Solution**: Check terminal compatibility:
```bash
echo $TERM  # Should be xterm-256color or similar
```

## Performance Optimization

### Termux

- Use `proot-distro` for better performance
- Disable unnecessary Termux services
- Use `nice` for background processes:
```bash
nice -n 10 python3 outclaw_dashboard.py
```

### Windows

- Use Windows Terminal for better rendering
- Disable Windows Defender real-time scanning for OutClaw directory (if safe)
- Use SSD for config directory

### Linux/Chromebook

- Use hardware acceleration if available
- Increase terminal buffer size
- Use `tmux` or `screen` for persistent sessions

## Security Considerations

### All Platforms

- Config files contain no secrets by default
- API keys stored in separate `.env` file (not in git)
- File permissions: `chmod 600 config.yaml`
- Regular updates: `git pull && bash install_dashboard.sh`

### Termux

- Use `termux-keystore` for sensitive data
- Enable device encryption
- Use VPN for remote access

### Windows

- Use Windows Credential Manager for secrets
- Enable BitLocker for config directory
- Use Windows Firewall rules

### Linux/Chromebook

- Use `gnome-keyring` or `kwallet` for secrets
- Enable full-disk encryption
- Use `ufw` firewall rules

## Next Steps

1. **Run Setup Wizard**: `python3 -m dashboard.setup_wizard`
2. **Test Dashboard**: `python3 outclaw_dashboard.py`
3. **Configure Integrations**: Enable rclone, ssh, printing as needed
4. **Customize Workflow**: Set up timeline and milestones
5. **Read Documentation**: See `DASHBOARD_QUICKSTART.md` for features

## Support

For platform-specific issues:
- Check `WHO_DID_WHAT.md` for recent changes
- Review `DASHBOARD_DESIGN.md` for architecture
- See `dashboard/platform.py` for platform detection code
- Run setup wizard for guided troubleshooting

---

**Last Updated**: 2026-07-27  
**Tested Platforms**: Termux, Windows 10/11, Ubuntu 22.04, Chromebook (Crostini)  
**Status**: ✅ Cross-platform support complete
