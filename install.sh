#!/usr/bin/env bash
# CredClaude — Install Script
# Builds .app bundle, copies to ~/Applications, registers launchd auto-start.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$HOME/.credclaude"
VENV_DIR="$SCRIPT_DIR/venv"
PLIST_NAME="com.veer.credclaude"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
APP_NAME="CredClaude"
APP_DEST="$HOME/Applications/$APP_NAME.app"

echo "=== CredClaude Installer ==="
echo ""

# 0. Quit any running instance before rebuilding
if pgrep -x "CredClaude" &>/dev/null; then
  echo "→ Stopping running CredClaude instance..."
  osascript -e 'tell application "CredClaude" to quit' 2>/dev/null || true
  sleep 1
  # Force-kill if still running after graceful quit
  pkill -x "CredClaude" 2>/dev/null || true
fi

# 1. Create venv
echo "→ Creating virtual environment..."
python3 -m venv "$VENV_DIR"

# 2. Install deps
echo "→ Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$SCRIPT_DIR"

# 3. Build .app bundle
echo "→ Building app bundle..."
bash "$SCRIPT_DIR/build_app.sh"

# 4. Copy to ~/Applications
echo "→ Installing to ~/Applications..."
mkdir -p "$HOME/Applications"
if [ -d "$APP_DEST" ]; then
  rm -rf "$APP_DEST"
fi
cp -R "$SCRIPT_DIR/dist/$APP_NAME.app" "$APP_DEST"

# 5. Create app support dir
mkdir -p "$APP_DIR"

# 6. Write launchd plist
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
    <string>open</string>
    <string>-a</string>
    <string>$APP_DEST</string>
  </array>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <false/>

  <!-- Note: stdout/stderr not captured here because 'open -a' spawns a
       separate process. App logs are written to ~/.credclaude/monitor.log
       by the Python logging module (RotatingFileHandler). -->
</dict>
</plist>
PLIST

# 7. Load the agent
if launchctl list "$PLIST_NAME" &>/dev/null; then
  echo "→ Reloading existing launchd agent..."
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi
launchctl load "$PLIST_PATH"

# 8. Launch the new version explicitly
# (launchctl load with RunAtLoad only fires on a fresh load — open ensures the
# app starts immediately in both fresh-install and update scenarios)
echo "→ Launching CredClaude..."
open "$APP_DEST"

echo ""
echo "✅ Installed! CredClaude is now running in your menu bar."
echo "   It will auto-start on every login."
echo ""
echo "   App:        $APP_DEST"
echo "   Config:     $APP_DIR/config.json"
echo "   Logs:       $APP_DIR/monitor.log"
echo "   Pricing:    $APP_DIR/pricing.json"
echo ""
echo "   To uninstall:  bash $SCRIPT_DIR/uninstall.sh"
