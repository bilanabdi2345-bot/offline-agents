#!/bin/bash
# Makes a clickable "Codicilix" app for your Mac. Run once:
#     ./scripts/make-mac-app.sh
# Then drag "Codicilix" from Applications into your Dock.
set -e
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
APP="$HOME/Applications/Codicilix.app"
[ -z "$PYTHON" ] && { echo "Please install Python 3 first."; exit 1; }

# Build the on-device screenshot reader (Apple Vision). Needs Xcode's command
# line tools, which come with git on a Mac. Skipped quietly if missing.
if command -v swiftc >/dev/null; then
  echo "Building the screenshot reader (about 30 seconds)..."
  mkdir -p "$PROJECT/bin"
  swiftc -O "$PROJECT/scripts/ocr.swift" -o "$PROJECT/bin/second-brain-ocr" \
    && echo "Screenshot reader ready." \
    || echo "Couldn't build the screenshot reader. Everything else still works."
  swiftc -O "$PROJECT/scripts/pdf.swift" -o "$PROJECT/bin/second-brain-pdf" \
    && echo "PDF reader ready." \
    || echo "Couldn't build the Mac PDF reader, so the simpler built-in one will be used."
else
  echo "Swift not found, so screenshots will be skipped. To add it: xcode-select --install"
fi

mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Codicilix</string>
  <key>CFBundleIdentifier</key><string>local.codicilix</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/launch" <<LAUNCH
#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:\$PATH"
# Start the local AI model app if it isn't running.
pgrep -iq ollama || open -a Ollama 2>/dev/null
# Start Codicilix fresh each time, with a new secret key. It opens its own
# window with that key. Nothing is lost by restarting, because nothing is saved.
pkill -f "secondbrain" 2>/dev/null; sleep 0.5
cd "$PROJECT" && nohup "$PYTHON" -B -m secondbrain >/dev/null 2>&1 &
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
# A double-click "Update Codicilix" button, next to the app.
# Written to a new file and then swapped in, so it is safe to rebuild while it is running.
CMD="$HOME/Applications/Update Codicilix.command"
cat > "$CMD.new" <<UPD
#!/bin/bash
/bin/bash "$PROJECT/scripts/update.sh"
echo
read -n 1 -s -r -p "Press any key to close this window."
UPD
chmod +x "$CMD.new"
mv -f "$CMD.new" "$CMD"

echo "Done: $APP"
if [ -z "$QUIET" ]; then
  echo "First time: right-click it and choose Open. Then drag it into your Dock."
  echo "To update later, double-click 'Update Codicilix' in Applications."
  open "$HOME/Applications"
fi
