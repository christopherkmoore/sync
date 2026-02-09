# devsync

Bidirectional dev environment sync over SSH. Built for syncing code between a personal machine and a work machine on the same network.

## Quick Start

### Personal machine (SSH server)

1. Enable Remote Login: System Settings > General > Sharing > Remote Login
2. Note your IP: `ipconfig getifaddr en0`

### Work machine (SSH client)

One-command bootstrap:

```bash
scp user@<personal-ip>:/path/to/devsync/setup.sh ~/setup.sh
bash ~/setup.sh
```

This copies devsync, installs it, adds a shell alias, and generates an SSH key.

Set up passwordless auth (one time):

```bash
ssh-keygen -t ed25519
ssh-copy-id user@<personal-ip>
```

## Usage

```bash
# Find SSH hosts on your network
devsync scan

# Create a sync profile
devsync init myproject \
  --host user@192.168.1.187 \
  --remote /Users/user/Code/myproject \
  --local ~/Documents/Github/myproject

# Sync files
devsync push myproject       # local -> remote
devsync pull myproject       # remote -> local

# Preview changes without syncing
devsync status myproject

# Manage profiles
devsync list                 # show all profiles
devsync remove myproject     # delete a profile

# Detailed help with examples
devsync help
```

## Configuration

Profiles are stored as JSON. Two locations are supported:

- **Global**: `~/.config/devsync/profiles.json`
- **Local**: `./devsync.json` (takes priority when present)

Use `--local-config` with init to create a local config file you can edit directly:

```bash
devsync init myproject --host user@ip --remote /path --local /path --local-config
vim devsync.json  # easy to update IPs, paths, excludes
```

### Default excludes

Every profile starts with these excludes:

```
.git  node_modules  __pycache__  .venv  venv  .DS_Store  *.pyc  .env  *.md
```

Add more with `--exclude`:

```bash
devsync init myproject --host user@ip --remote /path --local /path \
  --exclude "*.xcuserstate" --exclude "Pods"
```

## Files

```
devsync/
├── devsync.py      # CLI tool (single file, stdlib only)
├── pyproject.toml  # pip install config
├── start.sh        # runs devsync without manually activating venv
├── setup.sh        # one-command bootstrap for new machines
└── .gitignore
```

## Requirements

- Python 3.8+
- rsync (pre-installed on macOS and most Linux)
- SSH access between machines
