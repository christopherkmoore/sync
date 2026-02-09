#!/bin/bash
set -e

echo "=== devsync setup ==="

read -p "Install directory [$HOME/Code/devsync]: " DEVSYNC_DIR
DEVSYNC_DIR="${DEVSYNC_DIR:-$HOME/Code/devsync}"

# Detect shell config
if [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
else
    SHELL_RC="$HOME/.profile"
fi

# Create directory if needed
mkdir -p "$DEVSYNC_DIR"

# Copy files from remote if this is a fresh install
if [ ! -f "$DEVSYNC_DIR/devsync.py" ]; then
    read -p "Remote host (e.g. user@192.168.1.100): " REMOTE_HOST
    read -p "Remote devsync path (e.g. /Users/someone/Code/devsync): " REMOTE_PATH

    if [ -z "$REMOTE_HOST" ] || [ -z "$REMOTE_PATH" ]; then
        echo "Error: both remote host and path are required."
        exit 1
    fi

    echo "Copying devsync files..."
    scp "$REMOTE_HOST:$REMOTE_PATH/devsync.py" "$DEVSYNC_DIR/"
    scp "$REMOTE_HOST:$REMOTE_PATH/pyproject.toml" "$DEVSYNC_DIR/"
    scp "$REMOTE_HOST:$REMOTE_PATH/.gitignore" "$DEVSYNC_DIR/"
    scp "$REMOTE_HOST:$REMOTE_PATH/start.sh" "$DEVSYNC_DIR/"
    chmod +x "$DEVSYNC_DIR/start.sh"
fi

# Create venv and install
echo "Setting up Python environment..."
if [ ! -d "$DEVSYNC_DIR/.venv" ]; then
    python3 -m venv "$DEVSYNC_DIR/.venv"
fi
source "$DEVSYNC_DIR/.venv/bin/activate"
pip install --upgrade pip -q
pip install -e "$DEVSYNC_DIR" -q
echo "Installed devsync."

# Add shell alias
if ! grep -q "alias devsync=" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# devsync" >> "$SHELL_RC"
    echo "alias devsync='$DEVSYNC_DIR/start.sh'" >> "$SHELL_RC"
    echo "Added alias to $SHELL_RC"
else
    echo "Alias already exists in $SHELL_RC"
fi

# Generate SSH key if none exists
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
    echo "Generating SSH key..."
    ssh-keygen -t ed25519 -f "$HOME/.ssh/id_ed25519" -N ""
    echo ""
    echo "Run this to set up passwordless auth:"
    echo "  ssh-copy-id <user>@<remote-machine-ip>"
else
    echo "SSH key already exists."
fi

echo ""
echo "=== Done! ==="
echo "Restart your shell or run: source $SHELL_RC"
echo "Then try: devsync help"
