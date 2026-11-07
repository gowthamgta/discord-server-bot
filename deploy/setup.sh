#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu server (Oracle Cloud / Google Cloud free VM).
# Run from inside the uploaded bot folder:  bash deploy/setup.sh
set -euo pipefail

BOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BOT_USER="$(whoami)"

echo "==> Installing Python"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

echo "==> Creating virtual environment in $BOT_DIR/.venv"
python3 -m venv "$BOT_DIR/.venv"
"$BOT_DIR/.venv/bin/pip" install --upgrade pip
"$BOT_DIR/.venv/bin/pip" install -r "$BOT_DIR/requirements.txt"

if [ ! -f "$BOT_DIR/.env" ]; then
    echo "!! No .env file found. Copy your .env into $BOT_DIR before starting the bot."
fi
chmod 600 "$BOT_DIR/.env" 2>/dev/null || true

echo "==> Installing systemd service (auto-start on boot, auto-restart on crash)"
sed -e "s|__BOT_DIR__|$BOT_DIR|g" -e "s|__BOT_USER__|$BOT_USER|g" \
    "$BOT_DIR/deploy/discord-bot.service" | sudo tee /etc/systemd/system/discord-bot.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now discord-bot

echo
echo "==> Done. Useful commands:"
echo "    sudo systemctl status discord-bot     # is it running?"
echo "    journalctl -u discord-bot -f          # live logs"
echo "    sudo systemctl restart discord-bot    # restart after updating files"
