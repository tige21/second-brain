#!/bin/bash
set -e

echo "=== Second Brain Bot Deploy ==="

# Create virtualenv and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Create data directory
mkdir -p data

# Install and start systemd service
sudo cp second-brain.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable second-brain
sudo systemctl restart second-brain

echo ""
echo "✅ Deployed successfully!"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status second-brain    # check status"
echo "  journalctl -u second-brain -f         # live logs"
echo "  sudo systemctl restart second-brain   # restart"
