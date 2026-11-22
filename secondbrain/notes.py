"""Reads the manager's notes, straight from where they live, every time.

There is no index and no cache. Each question reads the files fresh into
memory, and that memory is thrown away when the answer is done.

Supported kinds of notes:
  .md .txt        written notes, meeting notes, drafts, scraps
  .csv            action-item lists
  .ics            calendar events and reminders
  .webloc .url    saved links
  .png .jpg .jpeg .heic  screenshots and photos (text read on this laptop)
"""

import csv
import datetime as dt
import hashlib
import io
import os
import re

from . import ocr

KINDS = {
    ".md": "note",
    ".txt": "note",
    ".csv": "action list",
    ".ics": "calendar",
    ".webloc": "saved link",
    ".url": "saved link",
    ".png": "screenshot or photo",
    ".jpg": "screenshot or photo",
    ".jpeg": "screenshot or photo",
    ".heic": "screenshot or photo",
}
ALL_KINDS = sorted(set(KINDS.values()))
MAX_FILE_BYTES = 512 * 1024

MONTHS = {
    m: i
    for i, names in enumerate(
        [
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for m in names
}


class Chunk:
    """One small piece of a note, with where it came from."""

    def __init__(self, compartment, path, rel, kind, text, line_start, line_end, date, date_source):
        self.compartment = compartment
        self.path = path
        self.rel = rel
        self.kind = kind
        self.text = text.strip()
        self.line_start = line_start
        self.line_end = line_end
        self.date = date
        self.date_source = date_source
        self.flags = []

    def to_dict(self, today):
        age = (today - self.date).days if self.date else None
        return {
            "compartment": self.compartment,
            "file": self.rel,
            "kind": self.kind,
            "lines": f"{self.line_start}-{self.line_end}" if self.line_end > self.line_start else str(self.line_start),
            "date": self.date.isoformat() if self.date else None,
            "date_label": nice_date(self.date) if self.date else "date unknown",
            "date_source": self.date_source,
            "age_days": age,
            "text": self.text,
            "flags": self.flags,
            "paste_id": getattr(self, "paste_id", None),
        }


def nice_date(d):
    return f"{d.day} {d.strftime('%b %Y')}"


def _year_fix(day, month, today, year=None):
    """Notes often skip the year. Pick the year that puts the date closest to today."""
    try:
        if year:
            return dt.date(year, month, day)
        candidates = [dt.date(today.year + k, month, day) for k in (-1, 0, 1)]
        return min(candidates, key=lambda d: abs((d - today).days))
    except ValueError:
        return None


def find_date(text, today):
    """Find the first date written in a piece of text, in many messy styles.
    If several dates appear, the one written first wins."""
    t = text.lower()
    found = []  # (position, date)

    def add(pos, d):
        if d is not None:
            found.append((pos, d))

    for m in re.finditer(r"(20\d\d)[-_/.](\d{1,2})[-_/.](\d{1,2})", t):
        add(m.start(), _year_fix(int(m.group(3)), int(m.group(2)), today, int(m.group(1))))
    for m in re.finditer(r"(20\d\d)(\d\d)(\d\d)t", t):  # calendar style 20261123T100000
        add(m.start(), _year_fix(int(m.group(3)), int(m.group(2)), today, int(m.group(1))))
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\b(?:\s+(20\d\d))?", t):
        if m.group(2) in MONTHS:
            y = int(m.group(3)) if m.group(3) else None
            add(m.start(), _year_fix(int(m.group(1)), MONTHS[m.group(2)], today, y))
    for m in re.finditer(r"\b([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\b", t):
        if m.group(1) in MONTHS:
            add(m.start(), _year_fix(int(m.group(2)), MONTHS[m.group(1)], today))
    for m in re.finditer(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(20\d\d))?(?![\d/])", t):  # UK style 4/11
        y = int(m.group(3)) if m.group(3) else None
        if 1 <= int(m.group(2)) <= 12:
            add(m.start(), _year_fix(int(m.group(1)), int(m.group(2)), today, y))
    return min(found)[1] if found else None


def _read_text(path):
    if os.path.getsize(path) > MAX_FILE_BYTES:
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _chunks_from_text(text, base):
    """Keep a short note whole. Split a long note by blank lines, then by size."""
    lines = text.splitlines()
    if len(text) <= 1500:
        return [base(text, 1, max(1, len(lines)))]
    pieces, start, buf = [], 1, []
    for i, line in enumerate(lines, start=1):
        if line.strip() == "":
            if buf:
                pieces.append((start, i - 1, buf))
                buf = []
            start = i + 1
            continue
        if not buf:
            start = i
        buf.append(line)
        if len(buf) >= 8:
            pieces.append((start, i, buf))
            buf = []
            start = i + 1
    if buf:
        pieces.append((start, start + len(buf) - 1, buf))

    # Keep the heading attached to each piece, so pieces make sense alone.
    heading = lines[0].strip() if lines else ""
    if len(pieces) > 1 and pieces[0][0] == pieces[0][1] == 1:
        pieces = pieces[1:]  # a heading on its own line is attached to every piece below
    out = []
    for s, e, b in pieces:
        body = "\n".join(b)
        if heading and s > 1 and heading not in body:
            body = f"{heading}\n{body}"
        out.append(base(body, s, e))
    return out


def _chunks_from_lines(text, base):
    """Scrap files where every line is its own note (like stand-up scraps)."""
    return [
        base(line, i, i)
        for i, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]


def _chunks_from_csv(text, base):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]
    out = []
    for i, row in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in row):
            continue
        parts = [f"{h}: {v.strip()}" for h, v in zip(header, row) if v.strip()]
        out.append(base("Action item — " + "; ".join(parts), i, i))
    return out


def _chunks_from_ics(text, base):
    out = []
    lines = text.splitlines()
    block, start, kind = [], 0, None
    for i, line in enumerate(lines, start=1):
        if line.startswith("BEGIN:VEVENT") or line.startswith("BEGIN:VTODO"):
            block, start, kind = [], i, "Event" if "VEVENT" in line else "Reminder"
        elif line.startswith("END:VEVENT") or line.startswith("END:VTODO"):
            fields = dict(l.split(":", 1) for l in block if ":" in l)
            summary = fields.get("SUMMARY", "(no title)")
            raw = fields.get("DTSTART") or fields.get("DUE") or ""
            m = re.match(r"(\d{4})(\d\d)(\d\d)(?:T(\d\d)(\d\d))?", raw)
            when = raw
            if m:
                d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                when = f"{d.strftime('%a')} {d.day} {d.strftime('%b %Y')}"
                if m.group(4):
                    when += f", {m.group(4)}:{m.group(5)}"
            out.append(base(f"{kind}: {summary} — {when}", start, i))
            kind = None
        elif kind:
            block.append(line)
    return out


def _chunks_from_link(text, rel, ext, base):
    if ext == ".webloc":
        m = re.search(r"<string>(.*?)</string>", text, re.S)
    else:
        m = re.search(r"^URL=(.*)$", text, re.M)
    url = m.group(1).strip() if m else "(no address found)"
    title = os.path.splitext(os.path.basename(rel))[0]
    return [base(f"Saved link: {title} — {url}", 1, 1)]


def _candidates(name, folder=None, files=None):
    """Every file a compartment covers: a whole folder, or a list of single files."""
    if files:
        for path in files:
            path = os.path.expanduser(path)
            if os.path.isfile(path):
                yield os.path.basename(path), path, os.path.join(name, os.path.basename(path))
        return
    folder = os.path.expanduser(folder or "")
    if not os.path.isdir(folder):
        return
    for root, dirs, names in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for fname in sorted(names):
            path = os.path.join(root, fname)
            yield fname, path, os.path.join(name, os.path.relpath(path, folder))


def read_compartment(name, folder, today, kinds=None, files=None):
    """Read every supported note in one folder (or in a list of single files).
    Returns (chunks, files_read). 'kinds' limits which kinds of content may be
    read (the user's choice)."""
    chunks, files_read, images = [], [], []
    files_list = files
    files = files_read
    for fname, path, rel in _candidates(name, folder, files_list):
        if True:
            ext = os.path.splitext(fname)[1].lower()
            if fname.startswith(".") or ext not in KINDS:
                continue
            kind = KINDS[ext]
            if kinds is not None and kind not in kinds:
                continue
            mtime = dt.date.fromtimestamp(os.path.getmtime(path))

            if kind == "screenshot or photo":
                images.append((path, rel, fname, mtime))
                continue

            text = _read_text(path)
            if text is None:
                continue
            files.append(rel)
            per_line = kind == "note" and ("scrap" in fname.lower() or "standup" in fname.lower())

            # When was this note written? Try the file name, then the first
            # two lines (the heading). Dates later in a note are often about
            # the future ("launch on 1 December"), so we do not use them.
            note_date, note_src = find_date(fname, today), "file name"
            if note_date is None and kind == "note":
                head = "\n".join(text.splitlines()[:2])
                note_date, note_src = find_date(head, today), "note heading"
            if note_date is not None and note_date > today:
                note_date = None
            if note_date is None:
                note_date, note_src = mtime, "file last changed"

            def base(body, s, e, _p=path, _r=rel, _k=kind, _nd=note_date, _ns=note_src,
                     _m=mtime, _pl=per_line):
                if _k == "calendar" or _pl:
                    d = find_date(body, today)
                    if d is not None:
                        return Chunk(name, _p, _r, _k, body, s, e, d, "written in the note")
                    return Chunk(name, _p, _r, _k, body, s, e, _m, "file last changed")
                return Chunk(name, _p, _r, _k, body, s, e, _nd, _ns)

            if ext == ".csv":
                new = _chunks_from_csv(text, base)
            elif ext == ".ics":
                new = _chunks_from_ics(text, base)
            elif ext in (".webloc", ".url"):
                new = _chunks_from_link(text, rel, ext, base)
            elif per_line:
                new = _chunks_from_lines(text, base)
            else:
                new = _chunks_from_text(text, base)
            chunks.extend(add_flags(c, today) for c in new)

    # Screenshots and photos: read their text on this laptop, all in one go.
    if images:
        texts = ocr.read_images([p for p, _, _, _ in images])
        for path, rel, fname, mtime in images:
            text = texts.get(path)
            files.append(rel)
            if not text:
                continue
            d, src = find_date(fname, today), "file name"
            if d is None or d > today:
                d, src = mtime, "file last changed"
            lines = text.count("\n") + 1
            c = Chunk(name, path, rel, "screenshot or photo", "[Text read from image]\n" + text, 1, lines, d, src)
            chunks.append(add_flags(c, today))
    return chunks, files


def add_flags(chunk, today):
    """Mark things a manager should be careful about. Done by code, not the AI,
    so these warnings are reliable."""
    t = chunk.text.lower()
    name = chunk.rel.lower()
    if "draft" in name or "[unfinished]" in t or "unfinished" in t:
        chunk.flags.append("unfinished draft")
    if chunk.kind == "action list" and "status: open" in t:
        m = re.search(r"due: (20\d\d-\d\d-\d\d)", t)
        if m and dt.date.fromisoformat(m.group(1)) < today:
            chunk.flags.append("overdue")
    if chunk.date and (today - chunk.date).days > 45 and chunk.kind == "note":
        chunk.flags.append("older than 6 weeks")
    if chunk.kind in ("note", "screenshot or photo") and re.search(
        r"ignore (all |any |your |previous )*(rules|instructions)|system message|"
        r"(send|email|upload|post) (it|this|everything|all)[^.]{0,40}(to|at) |https?://", t):
        chunk.flags.append("looks like instructions")
    if "confidential" in t or "private" in t:
        chunk.flags.append("marked private")
    return chunk


def fingerprint(folders):
    """A checksum of every note, so the user can see their notes are unchanged."""
    h = hashlib.sha256()
    count = 0
    for folder in folders:
        folder = os.path.expanduser(folder)
        walk = [(os.path.dirname(folder), [], [os.path.basename(folder)])] if os.path.isfile(folder) else os.walk(folder)
        for root, dirs, names in walk:
            dirs.sort()
            for fname in sorted(names):
                path = os.path.join(root, fname)
                try:
                    with open(path, "rb") as f:
                        h.update(path.encode())
                        h.update(f.read())
                    count += 1
                except OSError:
                    pass
    return h.hexdigest()[:16], count


def upcoming_events(chunks, today):
    """Calendar events from today onwards, soonest first."""
    events = [c for c in chunks if c.kind == "calendar" and c.text.startswith("Event:") and c.date and c.date >= today]
    return sorted(events, key=lambda c: c.date)
