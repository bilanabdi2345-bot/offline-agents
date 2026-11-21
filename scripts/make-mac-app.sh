#!/bin/bash
# Makes a clickable "Second Brain" app for your Mac. Run once:
#     ./scripts/make-mac-app.sh
# Then drag "Second Brain" from Applications into your Dock.
set -e
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
APP="$HOME/Applications/Second Brain.app"
[ -z "$PYTHON" ] && { echo "Please install Python 3 first."; exit 1; }

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Second Brain</string>
  <key>CFBundleIdentifier</key><string>local.second-brain</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/launch" <<LAUNCH
#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:\$PATH"
URL="http://127.0.0.1:8765"
# Start the local AI model app if it isn't running.
pgrep -iq ollama || open -a Ollama 2>/dev/null
# Start Second Brain if it isn't running. Its output goes nowhere: no log file.
if ! curl -s -o /dev/null "\$URL"; then
  cd "$PROJECT" && nohup "$PYTHON" -B -m secondbrain --no-browser >/dev/null 2>&1 &
  for i in \$(seq 1 30); do curl -s -o /dev/null "\$URL" && break; sleep 0.3; done
fi
open "\$URL"
LAUNCH
chmod +x "$APP/Contents/MacOS/launch"

if command -v sips >/dev/null && command -v iconutil >/dev/null; then
  SET="$(mktemp -d)/icon.iconset"; mkdir -p "$SET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$PROJECT/scripts/icon.png" --out "$SET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$PROJECT/scripts/icon.png" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$SET" -o "$APP/Contents/Resources/icon.icns"
fi
echo "Done: $APP"
echo "First time: right-click it and choose Open. Then drag it into your Dock."
open "$HOME/Applications"
