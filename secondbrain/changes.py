"""Finds things that changed across your notes, and promises you made, using
code only (no AI), so every line it shows is quoted from a note.

Idea from David's version of the project (github.com/davidxu16/ai-assistant):
"flag what changed since it was agreed" and "find promises you forgot".

- What changed: the same subject next to a different date or amount in
  different notes, e.g. "pilot 12 Jan" (12 Nov) then "pilot 26 Jan" (10 Dec).
  It also says which files still hold the old value, like an unfinished draft.
- What I owe: open actions that are yours, and lines where you wrote
  "I'll ...", "I need to ...", "me: ...".
"""

import datetime as dt
import re

from . import search

MONTHS = {m: i for i, names in enumerate([
    ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
    ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"),
    ("nov", "november"), ("dec", "december")], start=1) for m in names}
MON = "|".join(sorted(MONTHS, key=len, reverse=True))
DATE_RX = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({MON})\b|\b({MON})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
MONEY_RX = re.compile(r"([£$€])\s?(\d[\d,]*(?:\.\d+)?)\s?(k|m)?\b|\b(\d+(?:\.\d+)?)\s?(k|m)\b", re.I)
SELF_RX = re.compile(r"\b(i'll|i will|i said i'd|i need to|i promised|i owe|remind me to)\b|"
                     r"^\s*(?:[-*•]\s*)?(?:\[ \]\s*)?(?:me|todo me|action me)\s*[:\-]", re.I)

# Words too general to be "the subject" of a change.
GENERIC = set(search.tokens(
    "due date deadline by on from to until before after week weekly day today tomorrow monday tuesday wednesday "
    "thursday friday saturday sunday jan feb mar apr may jun jul aug sep oct nov dec month year time "
    "meeting sync call check-in standup notes note draft update new now moved move still says said "
    "status open done in progress at risk not started owner action item items next steps first version "
    "comment tracked change added crossed out page sheet line file back off holiday holidays break team "
    "list then also around about after"))


def _date(m, year_hint):
    if m.group(1):
        d, mon = int(m.group(1)), MONTHS[m.group(2).lower()]
    else:
        d, mon = int(m.group(4)), MONTHS[m.group(3).lower()]
    try:
        return dt.date(year_hint if mon >= 7 else year_hint + 1, mon, d)
    except ValueError:
        return None


def _values(line, year_hint):
    out = []
    for m in DATE_RX.finditer(line):
        d = _date(m, year_hint)
        if d:
            out.append(("date", d, m.start(), m.end()))
    for m in MONEY_RX.finditer(line):
        num = float((m.group(2) or m.group(4)).replace(",", ""))
        mult = {"k": 1e3, "m": 1e6}.get((m.group(3) or m.group(5) or "").lower(), 1)
        out.append(("money", num * mult, m.start(), m.end()))
    return out


def _fmt(kind, v):
    if kind == "money":
        return f"£{v / 1000:g}k" if v >= 1000 else f"£{v:g}"
    return f"{v.day} {v:%b}"


def _lines(chunks):
    """Every line of every note, with where it came from."""
    for c in chunks:
        if c.kind in ("calendar", "saved link"):
            continue
        for i, line in enumerate(c.text.splitlines()):
            if line.strip() and not line.startswith("[Text read from image]"):
                yield c, c.line_start + i, line.strip()


def _names(chunks):
    """People's names: words written with a capital letter in the middle of sentences."""
    seen = {}
    for c in chunks:
        for m in re.finditer(r"(?<=[a-z,;:] )([A-Z][a-z]{2,})\b", c.text):
            seen[m.group(1).lower()] = seen.get(m.group(1).lower(), 0) + 1
    return {n for n, k in seen.items() if k >= 2}


HEADER_RX = re.compile(r"^\[(Comment|Tracked change|Sticky note|Highlighted|Underlined|Note written on the page|Crossed out)[^:]*:\s*")
OLD_RX = re.compile(rf"\[crossed out: [^\]]*\]|\b(?:from|was)\s+(?:\d{{1,2}}\s+(?:{MON})|(?:{MON})\s+\d{{1,2}})(?=\s+(?:to|now)\b)", re.I)


def _subjects(line, s, prev_end, names):
    """What a date or amount is about: the first and last real words of its phrase."""
    seg = re.split(r"[.;:|(,\[\]]", line[prev_end:s])[-1]
    if not seg.strip() and ":" in line[prev_end:s]:
        seg = re.split(r"[.;|(,\[\]]", line[prev_end:s].rsplit(":", 1)[0])[-1]  # "Pilot start: 26 Jan"
    words = [w for w in search.tokens(seg) if w not in GENERIC and w not in names and not w[0].isdigit() and len(w) >= 4]
    if not words:
        return set()
    if re.search(r"\b(by|due|before)\s*$", seg, re.I):
        return {words[-1]}  # "send the list of pilot users by 15 Jan": the deadline is for the list, not the pilot
    return {words[0], words[-1]}


def what_changed(chunks, today):
    year_hint = today.year if today.month >= 7 else today.year - 1
    names = _names(chunks)
    per_file = {}   # (subject, kind) -> {file: {"values": set, "c", "n", "line"}}

    def note(w, kind, v, c, n, line, old=False):
        key = c.rel + ("#old" if old else "")
        f = per_file.setdefault((w, kind), {}).setdefault(key, {"values": set(), "c": c, "n": n, "line": line, "old": old})
        f["values"].add(v)

    for c, n, line in _lines(chunks):
        body = HEADER_RX.sub("", line)  # a comment's own date is when it was written, not what it's about
        olds = [m.group(0) for m in OLD_RX.finditer(body)]
        live = OLD_RX.sub(" ", body)
        prev_end = 0
        for kind, v, s, e in _values(live, year_hint):
            if kind == "date" and (v == c.date or re.search(r"w/c\s*$", live[:s], re.I)):
                prev_end = e
                continue
            subj = _subjects(live, s, prev_end, names)
            prev_end = e
            for w in subj:
                note(w, kind, v, c, n, line)
                for o in olds:  # "pilot moved from 12 Jan to 26 Jan": 12 Jan is the old value
                    for k2, v2, _, _ in _values(o, year_hint):
                        if k2 == kind:
                            note(w, kind, v2, c, n, line, old=True)
    stories = []
    for (w, kind), files in per_file.items():
        real = {k: f for k, f in files.items() if not f.get("old")}
        if any(len(f["values"]) > 1 for f in real.values()):
            continue  # one file lists several: that's a schedule, not a change
        if len(real) < 2 or len({next(iter(f["values"])) for f in real.values()}) < 2:
            continue
        items = sorted(((f["c"], f["n"], f["line"], v, f.get("old", False)) for f in files.values() for v in f["values"]),
                       key=lambda x: ((x[0].date or dt.date.min), not x[4]))
        seq = []
        for c, n, line, v, old in items:
            if old or "unfinished draft" in c.flags:
                continue
            if not seq or seq[-1][0] != v:
                seq.append((v, c, n, line))
        if len(seq) < 2:
            continue
        agree = [c for c, n, line, v, old in items if not old and v == seq[-1][0] and c is not seq[-1][1]]
        settled = [x for x in items if not x[4] and "unfinished draft" not in x[0].flags]
        latest_v = (settled or items)[-1][3]
        changed_on = next(c.date for c, n, line, v, old in items if v == latest_v)
        still_old = [(c, n, line, v) for c, n, line, v, old in items
                     if not old and v != latest_v and ("unfinished draft" in c.flags or (c.date and c.date >= changed_on))]
        stories.append({"subject": w, "kind": kind, "seq": seq, "latest": latest_v, "still_old": still_old, "agree": agree,
                        "files": set(real), "score": len(real) + 2 * len(still_old)})
    stories.sort(key=lambda s: -s["score"])
    out, used = [], []
    for s in stories:
        lines = {(c.rel, n) for _, c, n, _ in s["seq"]}
        if any(len(lines & u) >= 2 for u in used):
            continue
        used.append(lines)
        out.append(s)
    return out[:6]


def short(rel):
    """'Projects/2026-12-10 Demo to Medical team.md' -> 'Demo to Medical team'."""
    name = rel.split("/")[-1].rsplit(".", 1)[0]
    return re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", name)


def describe_change(s):
    steps = " → ".join(f"{_fmt(s['kind'], v)} ({short(c.rel)}, {c.date.day} {c.date:%b})" for v, c, n, line in s["seq"])
    text = f"{s['subject'].capitalize()}: {steps}."
    agree = sorted({short(c.rel) for c in s["agree"]})
    if agree:
        text += f" Also says {_fmt(s['kind'], s['latest'])}: {', '.join(agree)}."
    if s["still_old"]:
        olds = sorted({f"{short(c.rel)} still says {_fmt(s['kind'], v)}" for c, n, line, v in s["still_old"]})
        text += " Careful: " + "; ".join(olds) + "."
    return text


def short_change(s):
    """One plain line: 'The pilot moved from 12 Jan to 26 Jan. The handover draft still says 12 Jan.'"""
    first, last = s["seq"][0][0], s["seq"][-1][0]
    text = f"{s['subject'].capitalize()} moved from {_fmt(s['kind'], first)} to {_fmt(s['kind'], last)}."
    if s["still_old"]:
        c, n, line, v = s["still_old"][0]
        text += f" Careful: {short(c.rel)} still says {_fmt(s['kind'], v)}."
    return text


def what_i_owe(chunks, today):
    """Your open promises: open actions owned by you, and 'I'll ...' lines."""
    out = []
    for c in chunks:
        if c.kind == "action list":
            t = c.text.lower()
            if "status: open" in t and re.search(r"owner: (me|tommy)\b", t):
                out.append((c, c.line_start, c.text.strip(), "overdue" in c.flags))
            continue
        if c.kind in ("calendar", "saved link"):
            continue
        for i, line in enumerate(c.text.splitlines()):
            if SELF_RX.search(line) and "[x]" not in line.lower():
                out.append((c, c.line_start + i, line.strip(), False))
    out.sort(key=lambda x: (not x[3], -(x[0].date or dt.date.min).toordinal()))
    return out[:10]
