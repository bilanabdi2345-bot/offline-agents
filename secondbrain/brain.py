"""The assistant itself: read, find, ask the local model, explain.

Everything here lives in memory for one question only. Nothing is saved.
"""

import datetime as dt
import json
import os
import re
import time
import urllib.request

from . import notes, search

OLLAMA_URL = "http://127.0.0.1:11434"
FAKE_LLM = os.environ.get("FAKE_LLM") == "1"


def today():
    fixed = os.environ.get("TODAY")  # lets tests and demos fix the date
    return dt.date.fromisoformat(fixed) if fixed else dt.date.today()


class Compartments:
    """The folders the user has shared, and whether each is switched on.
    Held in memory only. The starting list comes from config.json."""

    def __init__(self, items):
        self.items = [dict(i) for i in items]

    def on(self):
        return [i for i in self.items if i["enabled"]]

    def set(self, name, enabled):
        for i in self.items:
            if i["name"] == name:
                i["enabled"] = bool(enabled)
                return True
        return False

    def add(self, name, path):
        name = re.sub(r"[^\w\- ]", "", name).strip() or "Folder"
        if any(i["name"] == name for i in self.items):
            return False, "A compartment with that name already exists."
        if not os.path.isdir(os.path.expanduser(path)):
            return False, "That folder doesn't exist."
        self.items.append({"name": name, "path": path, "enabled": True})
        return True, ""

    def remove(self, name):
        before = len(self.items)
        self.items = [i for i in self.items if i["name"] != name]
        return len(self.items) < before

    def describe(self, day):
        out = []
        for i in self.items:
            _, files = notes.read_compartment(i["name"], i["path"], day)
            out.append({**i, "files": len(files)})
        return out


SYSTEM = """You are a careful assistant helping a busy manager use their own notes.
Rules:
- Use ONLY the numbered sources given. Never use outside knowledge. Never guess.
- After each fact, write the source number in square brackets, like [2].
- Write short, plain sentences. Use short bullet points.
- If two sources disagree, trust the newer one, and say clearly that the older one is out of date.
- Point out unfinished drafts, overdue actions and private notes when they matter.
- If the sources do not answer something, say "I couldn't find" that in the notes."""


def build_prompt(question, picked, missing, day):
    lines = [f"Today is {notes.nice_date(day)} ({day.strftime('%A')}).", "", "SOURCES:"]
    for n, c in enumerate(picked, start=1):
        age = (day - c.date).days if c.date else None
        when = f"{notes.nice_date(c.date)}" + (f", {age} days ago" if age is not None and age >= 0 else "")
        flags = f" | WARNING: {', '.join(c.flags)}" if c.flags else ""
        lines.append(f"[{n}] {c.rel} ({c.kind}, {when}){flags}")
        lines.append(c.text)
        lines.append("")
    if missing:
        lines.append(f"These words from the question appear nowhere in the notes: {', '.join(missing)}.")
    lines += [
        "",
        f"QUESTION: {question}",
        "",
        "Answer with:",
        "1. The answer, as short bullet points with source numbers.",
        "2. A line starting 'Watch out:' for anything out of date, conflicting, unfinished, overdue or private. Skip it if there is nothing.",
        "3. A line starting 'Not in your notes:' for any part you could not find. Skip it if you found everything.",
    ]
    return "\n".join(lines)


def ask_model(prompt, model, keep_alive):
    if FAKE_LLM:
        if os.environ.get("FAKE_LLM_TEXT"):
            return os.environ["FAKE_LLM_TEXT"].replace("\\n", "\n")
        return "- Fake answer using the notes [1] and [2].\nWatch out: this is a test reply [1]."
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "keep_alive": int(keep_alive) if str(keep_alive).isdigit() else keep_alive,
            "options": {"temperature": 0.1, "num_ctx": 8192},
        }
    ).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["message"]["content"]


def model_status(model):
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
        return {"running": True, "model_ready": any(n.startswith(model) for n in names)}
    except Exception:
        return {"running": FAKE_LLM, "model_ready": FAKE_LLM}


def confidence(picked, cited, day):
    used = [picked[i - 1] for i in cited if 0 < i <= len(picked)]
    if not used:
        return "low", "The answer doesn't point to any of your notes, so treat it with care."
    newest = max(c.date for c in used if c.date)
    age = (day - newest).days
    warn = any(c.flags for c in used)
    if len(used) >= 2 and age <= 30 and not warn:
        return "high", f"Based on {len(used)} notes, the newest from {age} days ago."
    if len(used) >= 2 and age <= 30:
        return "medium", f"Based on {len(used)} notes, but some have warnings. Check the flagged ones."
    if age > 30:
        return "medium", f"The newest note used is {age} days old. Things may have changed since."
    return "medium", "Based on only one note."


def answer(question, compartments, model="llama3.2:3b", keep_alive="0"):
    started = time.time()
    day = today()
    question = question.strip()

    # 1. Read the switched-on compartments, fresh, into memory.
    chunks, files_read, skipped = [], [], []
    for comp in compartments.items:
        if not comp["enabled"]:
            skipped.append(comp["name"])
            continue
        c, f = notes.read_compartment(comp["name"], comp["path"], day)
        chunks += c
        files_read += f

    # 2. Find the pieces that match.
    hits, missing = search.search(question, chunks, today=day)
    picked = [c for _, c in hits]

    # 3. Explain where help came from, in plain words.
    def explain(used_files):
        parts = [f"I read {len(files_read)} files in: {', '.join(c['name'] for c in compartments.on()) or 'nothing'}."]
        if skipped:
            parts.append(f"I did not open {', '.join(skipped)}, because you switched {'it' if len(skipped) == 1 else 'them'} off.")
        if used_files:
            parts.append(f"The answer uses {len(used_files)} of them: {', '.join(used_files)}.")
        parts.append("I kept no copy. Everything I read is gone from my memory now.")
        return " ".join(parts)

    base = {
        "question": question,
        "today": day.isoformat(),
        "files_read": files_read,
        "skipped": skipped,
        "missing": missing,
    }

    # 4. Honest when it isn't there: no matches means no AI answer at all.
    if not picked:
        return {
            **base,
            "found": False,
            "answer": "I couldn't find anything about that in the notes you've shared."
            + (f" None of your notes mention: {', '.join(missing)}." if missing else "")
            + (f" {', '.join(skipped)} is switched off, so I didn't look there." if skipped else ""),
            "sources": [],
            "confidence": "none",
            "confidence_reason": "Nothing in your notes matched, so I didn't guess.",
            "explanation": explain([]),
            "seconds": round(time.time() - started, 1),
        }

    # 5. Ask the local model, then forget.
    text = ask_model(build_prompt(question, picked, missing, day), model, keep_alive)
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)})
    sources = []
    for n, c in enumerate(picked, start=1):
        d = c.to_dict(day)
        d["n"] = n
        d["used"] = n in cited
        sources.append(d)
    level, reason = confidence(picked, cited, day)
    used_files = sorted({s["file"] for s in sources if s["used"]})
    return {
        **base,
        "found": True,
        "answer": text,
        "sources": sources,
        "confidence": level,
        "confidence_reason": reason,
        "explanation": explain(used_files),
        "seconds": round(time.time() - started, 1),
    }


def meeting_question(compartments):
    """Turn the next calendar event into a 'prepare me' question."""
    day = today()
    chunks = []
    for comp in compartments.on():
        c, _ = notes.read_compartment(comp["name"], comp["path"], day)
        chunks += c
    events = notes.upcoming_events(chunks, day)
    if not events:
        return None
    ev = events[0]
    title = ev.text.split("—")[0].replace("Event:", "").strip()
    return {
        "title": title,
        "date": notes.nice_date(ev.date),
        "question": (
            f"Prepare me for my meeting '{title}' on {ev.date.strftime('%A')} {notes.nice_date(ev.date)}. "
            f"What happened last time, what actions are still open, what has changed, and what should I follow up on?"
        ),
    }
