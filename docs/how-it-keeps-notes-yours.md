# How Second Brain keeps your notes yours

## The One Rule

> The assistant may work with what is on the device, but nothing it reads leaves the device.
> The assistant does not keep its own copy.

## 1. Nothing leaves the device

- **Local AI.** The language model (Llama 3.2, 3 billion parameters) runs on the laptop through Ollama, at 127.0.0.1:11434.
- **Network guard.** Before the app reads a single note, it replaces Python's network functions with guarded versions. Only connections to this laptop (127.0.0.1, ::1, localhost) are allowed. Anything else is blocked, and DNS lookups for outside names are blocked too. Every allowed and blocked attempt is counted in memory and shown in the trust panel.
- **Local-only server.** The app window is served on 127.0.0.1 only, so no other device can reach it. It also rejects requests from other websites, by checking the Origin and Host headers and a custom header.

How a user can tell:
- **Try to break the rule.** The app deliberately tries to reach example.com and 8.8.8.8 and shows that both are blocked.
- **Ask my Mac what's connected.** The app runs the operating system's own `lsof` tool on both the app and the Ollama process, and lists every network connection. It's the Mac answering, not the app.
- **Turn Wi-Fi off.** Everything keeps working.

## 2. No copies

The usual way to build "chat with your notes" is to copy the notes into a vector database. That copy is exactly what the rule forbids. So Second Brain has:

- **No index.** Notes are read fresh from their folders for every question, scored in memory (BM25), then dropped. On a manager's scale of notes this takes milliseconds.
- **No database, cache or log file.** A write guard blocks the app from opening any file for writing. Python's own cache files are switched off too (`-B`).
- **The model forgets.** Each request asks Ollama to unload the model straight after answering (`keep_alive: 0`), so no conversation is held in its memory.
- **Forget this session.** This clears the in-memory list of which files were read.

How a user can tell: the trust panel shows "saved 0 files", and **Try to break the rule** also tries to save a copy of the notes and is blocked.

## 3. Notes stay exactly where they were

Notes are only opened read-only. When the app starts, it takes a fingerprint (a SHA-256 checksum) of every note, held in memory. The trust panel re-checks it live: "fingerprint matches the one taken at start".

## 4. You choose what it sees, and can change your mind

Notes are grouped into **compartments**, which are folders such as Team, Projects and Personal. Each one has an on/off switch. A switched-off compartment is never opened. It isn't just hidden from the AI: the files aren't read at all. Every answer says which compartments were skipped, and lists every file that was read.

This was our answer to "split the assistant into fragments": the assistant is one thing, but what it can see is split into sealed parts that the user controls.

## 5. Honest when unsure

- If no note matches, the AI model is **not asked at all**. Second Brain says "I couldn't find anything about that", and names the words that appear in none of the notes.
- Warnings are made by **code, not the AI**, so they are reliable:
  - *overdue*: an open action whose due date has passed,
  - *unfinished draft*: a draft file or one marked unfinished,
  - *older than 6 weeks*: things may have changed,
  - *marked private*: a note that says confidential or private.
- The AI is told to trust newer notes over older ones and to say when an older note is out of date. For example, the launch moved from 1 December to 19 January, but an unfinished draft still says 1 December.
- **Confidence** (high, medium or low) is worked out from how many notes were used, how recent they are, and whether they carry warnings. The reason is shown in plain words.

## 6. Coping with messy notes

- Dates in many styles: `2026-10-20`, `12 Oct`, `2 nov`, `4/11`, calendar timestamps. Missing years are inferred. Undated notes fall back to the file's last-changed date, and the app says so.
- Scrap files are split line by line, because each line is its own note.
- Five kinds of content: notes, action lists (CSV), calendar files (ICS), and saved links (.webloc, .url).

## Limits we know about

- The guards protect this app. Ollama is a separate program. The `lsof` check and the Wi-Fi-off test cover it, but a stronger version would run the model inside a sandbox with networking removed.
- A 3B model can still word things imperfectly. That is why the sources are always shown next to the answer, and why warnings come from code.
- Screenshots aren't read yet. On-device text recognition, such as Apple's Vision framework, would be the next step.
