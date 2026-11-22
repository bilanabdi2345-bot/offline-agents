#!/bin/bash
# Update Codicilix in one go:
#   1. take the newest codicilix*.zip from Downloads (or the latest from GitHub),
#   2. copy it into this project,
#   3. run the tests (stop if any fail),
#   4. save and push to GitHub,
#   5. rebuild the app and reopen it.
set -e
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"

# Safety stop: only ever work inside the Codicilix project folder.
if [ "$PROJECT" = "/" ] || [ "$PROJECT" = "$HOME" ] || \
   [ ! -f "$PROJECT/secondbrain/__main__.py" ] || [ ! -d "$PROJECT/.git" ]; then
  echo "Safety stop: this updater must stay in the scripts folder of the Codicilix project."
  echo "Nothing was changed."
  exit 1
fi
cd "$PROJECT"
say() { printf "\n\033[1m%s\033[0m\n" "$1"; }

say "1. Looking for a new update..."
ZIP="$(ls -t "$HOME"/Downloads/codicilix*.zip 2>/dev/null | head -1 || true)"
STAMP="$PROJECT/.git/codicilix-last-zip"
if [ -n "$ZIP" ] && [ "$(cat "$STAMP" 2>/dev/null)" != "$(stat -f '%N %m' "$ZIP" 2>/dev/null || stat -c '%n %Y' "$ZIP")" ]; then
  echo "Found: $(basename "$ZIP")"
  TMP="$(mktemp -d)"
  unzip -q "$ZIP" -d "$TMP"
  # If the zip holds one folder, use what's inside it.
  SRC="$TMP"; [ "$(ls -A "$TMP" | wc -l | tr -d ' ')" = "1" ] && [ -d "$TMP/$(ls -A "$TMP")" ] && SRC="$TMP/$(ls -A "$TMP")"
  if [ ! -d "$SRC/secondbrain" ]; then echo "That zip doesn't look like Codicilix. Stopping."; exit 1; fi
  rsync -a --delete --exclude ".git" --exclude "bin" --exclude ".env" --exclude ".DS_Store" "$SRC/" "$PROJECT/"
  rm -rf "$TMP"
  stat -f '%N %m' "$ZIP" > "$STAMP" 2>/dev/null || stat -c '%n %Y' "$ZIP" > "$STAMP"
  FROM="zip $(basename "$ZIP")"
else
  echo "No new zip in Downloads. Checking GitHub instead..."
  git pull --ff-only || { echo "Couldn't get updates from GitHub."; exit 1; }
  FROM="GitHub"
fi

say "2. Running the tests..."
if ! python3 -B -m unittest discover tests; then
  echo; echo "Tests failed, so nothing was pushed. Send the message above to Claude."
  exit 1
fi

say "3. Saving to GitHub..."
git add -A
if git diff --cached --quiet; then
  echo "Nothing new to save."
else
  git commit -q -m "Update Codicilix (from $FROM)"
  git pull --rebase -q || true
  git push -q && echo "Pushed to GitHub." || echo "Couldn't push. Check your internet or GitHub login."
fi

say "4. Rebuilding and reopening the app..."
QUIET=1 "$PROJECT/scripts/make-mac-app.sh" >/dev/null
open "$HOME/Applications/Codicilix.app"

say "All done. Codicilix is up to date and open."
