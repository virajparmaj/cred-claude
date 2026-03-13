#!/usr/bin/env bash
# Claude Usage Monitor — Uninstall Script

PLIST_NAME="com.veer.claude-usage-monitor"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo "=== Uninstalling Claude Usage Monitor ==="

if launchctl list "$PLIST_NAME" &>/dev/null; then
  echo "→ Stopping launchd agent..."
  launchctl unload "$PLIST_PATH" 2>/dev/null || true
fi

if [ -f "$PLIST_PATH" ]; then
  rm "$PLIST_PATH"
  echo "→ Removed login item."
fi

echo "✅ Uninstalled. App files remain at ~/Work/Projects/claude-usage-monitor"
echo "   Delete that folder manually if you want a full clean removal."
