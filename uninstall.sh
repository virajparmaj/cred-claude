#!/usr/bin/env bash
# CredClaude — Uninstall Script
# Stops the launchd agent, removes the plist, and removes the .app bundle.

PLIST_NAME="com.veer.credclaude"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
APP_NAME="CredClaude"
APP_DEST="$HOME/Applications/$APP_NAME.app"

echo "=== Uninstalling CredClaude ==="

# Quit the running app before removing files
if pgrep -x "CredClaude" &>/dev/null; then
  echo "→ Stopping CredClaude..."
  osascript -e 'tell application "CredClaude" to quit' 2>/dev/null || true
  sleep 1
  pkill -x "CredClaude" 2>/dev/null || true
fi

# Stop and unload launchd agent
if launchctl list "$PLIST_NAME" &>/dev/null; then
  echo "→ Stopping launchd agent..."
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

# Remove plist
if [ -f "$PLIST_PATH" ]; then
  rm "$PLIST_PATH"
  echo "→ Removed login item."
fi

# Remove .app
if [ -d "$APP_DEST" ]; then
  rm -rf "$APP_DEST"
  echo "→ Removed $APP_DEST"
fi

echo ""
echo "✅ Uninstalled."
echo "   Config and logs remain at ~/.credclaude/"
echo "   Delete that folder manually for a full clean removal:"
echo "     rm -rf ~/.credclaude"
