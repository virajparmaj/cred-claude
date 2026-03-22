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
  <string>CredClaude</string>
  <key>LSUIElement</key>
  <true/>
  <key>LSBackgroundOnly</key>
  <false/>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
</dict>
</plist>
PLIST

# Compiled launcher stub — gives macOS the correct process identity
# so Stage Manager / Dock show "CredClaude" instead of "Python".
LAUNCHER_SRC="$MACOS/launcher.c"
cat > "$LAUNCHER_SRC" <<'CSRC'
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <libgen.h>
#include <mach-o/dyld.h>

int main(int argc, char *argv[]) {
    /* Resolve the directory containing this executable */
    char exe[4096];
    uint32_t sz = sizeof(exe);
    if (_NSGetExecutablePath(exe, &sz) != 0) {
        fprintf(stderr, "CredClaude: cannot resolve executable path\n");
        return 1;
    }
    char *real = realpath(exe, NULL);
    if (!real) { perror("realpath"); return 1; }
    char *dir = dirname(real);           /* .../Contents/MacOS */
    char *contents = dirname(dir);       /* .../Contents        */
    char *app_dir = dirname(contents);   /* .../CredClaude.app  */

    /* Walk up from the .app bundle to find the repo root.
       Installed layout: ~/Applications/CredClaude.app  →  repo is at REPO_DIR
       Dev layout:       <repo>/dist/CredClaude.app     →  repo is dirname(dirname(app_dir))
       We use the CREDCLAUDE_REPO env var if set, otherwise assume the
       repo path was baked in at build time (see sed below). */
    const char *repo = getenv("CREDCLAUDE_REPO");
    if (!repo) repo = "@@REPO_DIR@@";

    /* Validate venv */
    char venv_python[4096];
    snprintf(venv_python, sizeof(venv_python), "%s/venv/bin/python", repo);
    if (access(venv_python, X_OK) != 0) {
        /* Show a dialog via osascript */
        system("osascript -e 'display dialog \"CredClaude: venv not found.\\n"
               "The source repo may have moved.\\n"
               "Please re-run install.sh.\" buttons {\"OK\"} "
               "default button \"OK\" with icon stop' 2>/dev/null");
        free(real);
        return 1;
    }

    /* chdir to repo so relative imports work */
    chdir(repo);

    /* exec the Python interpreter — this process becomes Python but
       macOS already registered our binary name as "CredClaude". */
    char *new_argv[] = { "CredClaude", "-m", "credclaude", NULL };
    execv(venv_python, new_argv);

    /* If exec fails */
    perror("execv");
    free(real);
    return 1;
}
CSRC

# Bake in the repo path
sed -i '' "s|@@REPO_DIR@@|$SCRIPT_DIR|g" "$LAUNCHER_SRC"

# Compile the launcher
echo "   Compiling launcher stub..."
cc -O2 -o "$MACOS/CredClaude" "$LAUNCHER_SRC"
rm "$LAUNCHER_SRC"

echo "✅ Built: $APP_DIR"
echo "   Copy to ~/Applications/ to use."
