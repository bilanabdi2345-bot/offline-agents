# Second Brain

A private assistant for a manager's scattered notes.
It runs only on your laptop. Nothing it reads ever leaves the laptop.
It keeps no copy of your notes.

Built for the Pfizer AI Studio and Newpage hackathon, University of Bristol, November 2026.

## The moment it fixes

You have a 1:1 in ten minutes. Your notes about that person are spread across
meeting notes, an action list, stand-up scraps and a calendar reminder.

Click **Prepare me**. Second Brain gathers what matters:
- what happened last time,
- which actions are still open or overdue,
- what has changed since,
- what to follow up on.

Every fact links to the exact note it came from.
It warns you when a note is out of date, unfinished or private.
When something isn't in your notes, it says so instead of guessing.

## How it keeps your notes yours

| Promise | How it's done | How you can check |
|---|---|---|
| Nothing leaves the laptop | The AI model (Llama 3.2, 3B) runs locally with Ollama. A network guard inside the app blocks every connection that isn't to this laptop, including DNS lookups. | Click **Try to break the rule**: the app tries to reach the internet and is blocked. Click **Ask my Mac what's connected**: macOS lists every open connection. Or turn Wi-Fi off; it still works. |
| No copies | No database, no search index, no cache, no log file. Notes are read fresh for each question, in memory, then dropped. A write guard blocks the app from saving any file. The model is unloaded after every answer. | The trust panel shows "saved 0 files". **Try to break the rule** also tries to save a copy and is blocked. |
| Your notes stay as they were | Files are only ever opened read-only. | A fingerprint of all notes is taken at start and re-checked live. |
| You choose what it sees | Notes are split into compartments (Team, Projects, Personal). Switched off means never opened. | Switch Personal off and ask about it: the answer says it didn't look there, and the file list proves it. |
| Honest when unsure | If nothing matches, the AI isn't even asked; you get "I couldn't find that". Warnings for overdue, unfinished, old and private notes come from code, not the AI. | Ask about something that isn't there, e.g. "the Q2 budget for Lagos". |
| Explains itself | Every answer lists the files read, the files used, dates and ages, and a confidence level with the reason. | Click any numbered source chip. |

More detail: [docs/how-it-keeps-notes-yours.md](docs/how-it-keeps-notes-yours.md)

## Set it up (Mac, about 10 minutes, needs internet once)

1. Install **Ollama** from ollama.com/download and open it.
2. In Terminal, download the AI model:
   ```sh
   ollama pull llama3.2:3b
   ```
3. Get this project and make the app:
   ```sh
   git clone https://github.com/bilanabdi2345-bot/offline-agents.git
   cd offline-agents
   ./scripts/make-mac-app.sh
   ```
4. In Applications, right-click **Second Brain** and choose **Open** (first time only).

You can now turn Wi-Fi off. It keeps working.

**Without the app icon:** run `python3 -B -m secondbrain` in the project folder.
It opens http://127.0.0.1:8765 in your browser.

## Use your own notes

Edit `config.json`. Add a compartment with a name and a folder path:

```json
{ "name": "Meetings", "path": "~/Documents/Meeting notes", "enabled": true }
```

Or click **+ Add a folder** in the app (this lasts until you close it).
It reads `.md`, `.txt`, `.csv` action lists, `.ics` calendar files and saved links (`.webloc`, `.url`).

## Sample notes

`sample-notes/` holds made-up notes for a made-up manager, written for this demo.
They are messy on purpose: a launch date that was changed later, an unfinished
draft that still has the old date, overdue actions, scraps with no dates, and a
private folder.

## Run the tests

```sh
python3 -B -m unittest discover tests
```

17 tests. They use a fake AI model, so they run anywhere.

## Project layout

```
secondbrain/
  guards.py     the network guard and the write guard
  notes.py      reads notes fresh, finds dates, flags problems
  search.py     finds matching notes for each question (no saved index)
  brain.py      builds the answer with the local AI model, explains it
  trust.py      the checks behind the trust panel
  server.py     the local web server (127.0.0.1 only)
  static/       the app window
sample-notes/   made-up notes for the demo
scripts/        Mac app maker and stop script
tests/          automatic tests
docs/           design notes, demo script
```
