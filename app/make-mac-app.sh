#!/bin/bash
# Makes a clickable "Offline Agents" app for your Mac.
# Run it once from the project folder:
#     ./app/make-mac-app.sh
# Then drag "Offline Agents" from your Applications folder into your Dock.
#
# When you click the app it:
#   1. opens Docker Desktop if it is not open yet,
#   2. starts the agents,
#   3. starts the chat app server,
#   4. opens the chat page in your browser.
set -e

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
APP="$HOME/Applications/Offline Agents.app"

if [ -z "$PYTHON" ]; then
  echo "Could not find python3. Please install Python first."
  exit 1
fi

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Offline Agents</string>
  <key>CFBundleDisplayName</key><string>Offline Agents</string>
  <key>CFBundleIdentifier</key><string>local.offline-agents</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/launch" <<LAUNCH
#!/bin/bash
# Apps opened from the Dock do not see your normal terminal settings,
# so we tell it where to find Docker and Python.
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:\$PATH"
PROJECT="$PROJECT"
PYTHON="$PYTHON"
URL="http://127.0.0.1:8765"
LOG="\$HOME/Library/Logs/offline-agents.log"

cd "\$PROJECT" || exit 1

# 1. Open Docker Desktop and wait until it is ready.
if ! docker info >/dev/null 2>&1; then
  open -a Docker
  for i in \$(seq 1 60); do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
fi

# 2. Start the agents.
docker compose up -d >>"\$LOG" 2>&1

# 3. Start the chat app server, if it is not already running.
if ! curl -s -o /dev/null "\$URL"; then
  nohup "\$PYTHON" "\$PROJECT/app/server.py" >>"\$LOG" 2>&1 &
  for i in \$(seq 1 20); do
    curl -s -o /dev/null "\$URL" && break
    sleep 0.5
  done
fi

# 4. Open the chat page.
open "\$URL"
LAUNCH

chmod +x "$APP/Contents/MacOS/launch"

# Make a simple icon from the project's icon picture, if the Mac tools exist.
if [ -f "$PROJECT/app/icon.png" ] && command -v sips >/dev/null && command -v iconutil >/dev/null; then
  ICONSET="$(mktemp -d)/icon.iconset"
  mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$PROJECT/app/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$PROJECT/app/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icon.icns"
fi

echo "Done. Your app is here: $APP"
echo "Open your Applications folder and drag 'Offline Agents' into your Dock."
open "$HOME/Applications"
