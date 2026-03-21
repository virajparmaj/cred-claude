#!/usr/bin/env bash
# Build a macOS .app bundle using a shell wrapper approach.
# This creates a minimal .app that launches the Python package via the venv.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="CredClaude"
APP_DIR="$SCRIPT_DIR/dist/$APP_NAME.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"

# Read version from package (single source of truth)
if [ -d "$SCRIPT_DIR/venv" ]; then
  VERSION=$("$SCRIPT_DIR/venv/bin/python" -c "import credclaude; print(credclaude.__version__)" 2>/dev/null || echo "1.0.0")
else
  VERSION="1.0.0"
fi

echo "→ Building $APP_NAME.app (v$VERSION)..."

# Clean previous build
rm -rf "$APP_DIR"

# Create .app structure
mkdir -p "$MACOS" "$RESOURCES"

# Build AppIcon.icns from the circular PNG logo
ICONSET="$RESOURCES/AppIcon.iconset"
mkdir -p "$ICONSET"
for size in 16 32 128 256 512; do
  sips -z $size $size "$SCRIPT_DIR/claude_monitor_logo.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z $double $double "$SCRIPT_DIR/claude_monitor_logo.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$RESOURCES/AppIcon.icns"
rm -rf "$ICONSET"
echo "   Icon: $RESOURCES/AppIcon.icns"

# Info.plist
cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>$APP_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>$APP_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>com.veer.credclaude</string>
  <key>CFBundleVersion</key>
  <string>$VERSION</string>
  <key>CFBundleShortVersionString</key>
  <string>$VERSION</string>
  <key>CFBundleExecutable</key>
  <string>launch</string>
  <key>LSUIElement</key>
  <true/>
  <key>LSBackgroundOnly</key>
  <false/>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
</dict>
</plist>
PLIST

# Launcher script — runs the Python package via the repo's venv
cat > "$MACOS/launch" <<LAUNCHER
#!/usr/bin/env bash
# CredClaude launcher
REPO_DIR="$SCRIPT_DIR"

# Validate venv exists (fails visibly if repo was moved after install)
if [ ! -d "\$REPO_DIR/venv" ]; then
  osascript -e 'display dialog "CredClaude: venv not found.\nThe source repo may have moved.\nPlease re-run install.sh." buttons {"OK"} default button "OK" with icon stop' 2>/dev/null
  exit 1
fi

cd "\$REPO_DIR"
exec "\$REPO_DIR/venv/bin/python" -m credclaude
LAUNCHER

chmod +x "$MACOS/launch"

echo "✅ Built: $APP_DIR"
echo "   Copy to ~/Applications/ to use."
