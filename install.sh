#!/usr/bin/env bash
# Claude Usage Monitor — Install Script
# Creates a venv, installs deps, and registers as a login item via launchd.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.claude-usage-monitor"
VENV_DIR="$SCRIPT_DIR/venv"
PLIST_NAME="com.veer.claude-usage-monitor"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
PYTHON="$VENV_DIR/bin/python"

echo "=== Claude Usage Monitor Installer ==="
echo ""

# 1. Create venv
echo "→ Creating virtual environment..."
python3 -m venv "$VENV_DIR"

# 2. Install deps
echo "→ Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"

# 3. Create app support dir
mkdir -p "$APP_DIR"

# 4. Write launchd plist
echo "→ Registering login item with launchd..."
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$PLIST_NAME</string>

  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$SCRIPT_DIR/monitor.py</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>$APP_DIR/monitor.log</string>

  <key>StandardErrorPath</key>
  <string>$APP_DIR/monitor.err</string>
</dict>
</plist>
PLIST

# 5. Load the agent now
if launchctl list "$PLIST_NAME" &>/dev/null; then
  echo "→ Reloading existing launchd agent..."
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi
launchctl load "$PLIST_PATH"

echo ""
echo "✅ Installed! Claude Usage Monitor is now running in your menu bar."
echo "   It will auto-start on every login."
echo ""
echo "   To uninstall:  bash uninstall.sh"
echo "   Logs:          $APP_DIR/monitor.log"
