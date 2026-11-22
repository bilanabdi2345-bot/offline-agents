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
mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1"; }
LAST_SAVE="$(git log -1 --format=%ct 2>/dev/null || echo 0)"
# Only use a zip that is newer than the last saved change (so old zips never undo new work).
if [ -n "$ZIP" ] && [ "$(mtime "$ZIP")" -gt "$LAST_SAVE" ]; then
  echo "Found a new zip: $(basename "$ZIP")"
  TMP="$(mktemp -d)"
  unzip -q "$ZIP" -d "$TMP"
  # If the zip holds one folder, use what's inside it.
  SRC="$TMP"; [ "$(ls -A "$TMP" | wc -l | tr -d ' ')" = "1" ] && [ -d "$TMP/$(ls -A "$TMP")" ] && SRC="$TMP/$(ls -A "$TMP")"
  if [ ! -d "$SRC/secondbrain" ]; then echo "That zip doesn't look like Codicilix. Stopping."; exit 1; fi
  rsync -a --delete --exclude ".git" --exclude "bin" --exclude ".env" --exclude ".DS_Store" "$SRC/" "$PROJECT/"
  rm -rf "$TMP"
  FROM="zip $(basename "$ZIP")"
elif [ -n "$(git status --porcelain)" ]; then
  echo "Found changes Claude made in this folder."
  FROM="Claude"
else
  echo "Nothing new here. Checking GitHub..."
  git pull --ff-only -q || echo "Couldn't check GitHub, carrying on."
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
