#!/bin/bash
set -e

DEVSYNC_DIR="$HOME/Code/devsync"
SHELL_RC="$HOME/.zshrc"

echo "=== devsync setup ==="

# Create directory if needed
mkdir -p "$DEVSYNC_DIR"

# Copy files from remote if this is a fresh install
if [ ! -f "$DEVSYNC_DIR/devsync.py" ]; then
    read -p "Remote host (e.g. christophermoore@192.168.1.187): " REMOTE_HOST
    read -p "Remote devsync path [/Users/christophermoore/Code/devsync]: " REMOTE_PATH
    REMOTE_PATH="${REMOTE_PATH:-/Users/christophermoore/Code/devsync}"

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
    echo "  ssh-copy-id christophermoore@<your-personal-machine-ip>"
else
    echo "SSH key already exists."
fi

echo ""
echo "=== Done! ==="
echo "Restart your shell or run: source $SHELL_RC"
echo "Then try: devsync help"
