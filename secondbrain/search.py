"""Finds the pieces of notes that match a question.

It scores every piece fresh for each question, in memory (BM25 scoring).
No search index is built or saved, because an index would be a copy.
"""

import datetime as dt
import difflib
import math
import re
from collections import Counter

STOP = set(
    """a about above after again all am an and any are as at be been before being
    below between both but by can could did do does doing down during each few for
    from further had has have having he her here hers herself him himself his how i
    if in into is it its itself just me more most my myself no nor not now of off on
    once only or other our ours out over own same she should so some such than that
    the their theirs them then there these they this those through to too under until
    up very was we were what when where which while who whom why will with would you
    your yours yourself tell show give find get got know need needs please help
    prepare prep ready meeting meetings next last time thing things anything something
    remind recap summary summarise summarize update latest happened happen says said
    did decide decided decision decisions change changed changes still
    monday tuesday wednesday thursday friday saturday sunday today tomorrow yesterday
    january february march april june july august september october november december
    jan feb mar apr jun jul aug sep sept oct nov dec week weeks month months day days
    past recent recently lately upcoming coming made make happening middle holiday holidays
    break christmas before
    wrote write written writing show tell read look see think thinks thinking""".split()
)
# Words like "decision" are in STOP for matching, but we still use them to
# give a small boost to pieces that record decisions.
BOOSTS = {
    "decision": ("decision", "decided", "agreed", "moved"),
    "action": ("action", "todo", "follow up", "status: open"),
}


# Words that describe a kind of note, so "my handwritten note" finds the
# notebook photo and "my calendar" finds calendar entries.
KIND_WORDS = {
    "screenshot or photo": "photo image picture screenshot handwritten handwriting notebook paper whiteboard scan",
    "calendar": "calendar meeting event diary",
    "action list": "action todo task list",
    "saved link": "link bookmark website",
    "note": "",
}


def stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text):
    words = re.findall(r"[a-z0-9]+(?::[0-9]+)?", text.lower())
    return [stem(w) for w in words if w not in STOP and len(w) > 1]


def fix_spelling(question, vocab):
    """Forgive typos: match each unknown word to the closest word that really
    appears in the notes (or to a common word we ignore). Returns
    (corrected question, list of (typed, understood))."""
    fixes = []
    stops = sorted(STOP)
    vocab_list = sorted(vocab)

    def fix(m):
        word = m.group(0)
        low = word.lower()
        if len(low) < 4 or low.isdigit() or low in STOP or stem(low) in vocab:
            return word
        near_stop = difflib.get_close_matches(low, stops, n=1, cutoff=0.8)
        if near_stop:
            return near_stop[0]  # e.g. "worte" -> "wrote", which we then ignore
        near = difflib.get_close_matches(stem(low), vocab_list, n=1, cutoff=0.78)
        if near:
            fixes.append((word, near[0]))
            return near[0]
        return word

    return re.sub(r"[A-Za-z]+", fix, question), fixes


def keywords(question):
    """The meaningful words in a question, as the user wrote them."""
    seen, out = set(), []
    for w in re.findall(r"[A-Za-z0-9]+", question):
        lw = w.lower()
        if lw in STOP or len(lw) < 3 or lw in seen:
            continue
        seen.add(lw)
        out.append(w)
    return out


def time_window(question, today):
    """Understand questions about time, like 'this week' or 'yesterday'.
    Returns (first day, last day) or None."""
    if today is None:
        return None
    q = question.lower()
    d = dt.timedelta
    rules = [
        ("before the holiday", (today - d(35), today - d(14))),
        ("before the break", (today - d(35), today - d(14))),
        ("before christmas", (today - d(35), today - d(14))),
        ("yesterday", (today - d(1), today - d(1))),
        ("today", (today, today)),
        ("next week", (today, today + d(7))),
        ("upcoming", (today, today + d(14))),
        ("coming up", (today, today + d(14))),
        ("last week", (today - d(14), today - d(7))),
        ("this week", (today - d(7), today)),
        ("past week", (today - d(7), today)),
        ("last 7 days", (today - d(7), today)),
        ("this month", (today - d(30), today)),
        ("last month", (today - d(30), today)),
        ("past month", (today - d(30), today)),
        ("recently", (today - d(14), today)),
        ("lately", (today - d(14), today)),
    ]
    for phrase, window in rules:
        if phrase in q:
            return window
    return None


def _spread(scored, top_k, per_file):
    picked, per = [], Counter()
    for s, c in scored:
        limit = per_file if c.kind == "note" else 2 if c.kind == "calendar" else 4
        if per[c.rel] < limit:
            picked.append((s, c))
            per[c.rel] += 1
    return picked[:top_k]


def doc_tokens(c):
    return tokens(c.text + " " + c.rel + " " + " ".join(c.flags) + " " + KIND_WORDS.get(c.kind, ""))


def search(question, chunks, top_k=10, k1=1.4, b=0.75, per_file=2, today=None, report=None, extra=None):
    """Return (best pieces with scores, keywords not found anywhere).
    If 'report' is a dict, spelling fixes are added to it."""
    vocab = set()
    docs_all = [doc_tokens(c) for c in chunks]
    for d in docs_all:
        vocab.update(d)
    question, fixes = fix_spelling(question, vocab)
    if report is not None:
        report["spelling"] = fixes
    q = tokens(question)
    # Related words (from the local AI) count for half as much as the user's own words.
    q_extra = [w for w in tokens(" ".join(extra or [])) if w not in q]
    window = time_window(question, today)
    ql = question.lower()
    wants = [k for k, words in BOOSTS.items() if k in ql or any(w in ql for w in words)]

    if window:
        start, end = window
        chunks = [c for c in chunks if c.date and start <= c.date <= end]
        if not q:
            # A question only about time: newest first, decisions/actions first if asked.
            def rank(c):
                text = c.text.lower()
                hit = any(any(w in text for w in BOOSTS[k]) for k in wants)
                return (not hit, -(c.date.toordinal()))
            ordered = sorted(chunks, key=rank)
            return _spread([(1.0, c) for c in ordered], top_k, per_file), []

    if not q or not chunks:
        return [], keywords(question)

    docs = [doc_tokens(c) for c in chunks]
    n = len(docs)
    avg = sum(len(d) for d in docs) / n or 1
    df = Counter()
    for d in docs:
        df.update(set(d))

    scored = []
    for chunk, d in zip(chunks, docs):
        tf = Counter(d)
        score = 0.0
        for term, weight in [(x, 1.0) for x in set(q)] + [(x, 0.5) for x in set(q_extra)]:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += weight * idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(d) / avg))
        if score > 0:
            text = chunk.text.lower()
            for k in wants:
                if any(w in text for w in BOOSTS[k]):
                    score *= 1.3
            # Newer notes matter more: things change, decisions get reversed.
            if today and chunk.date:
                age = (today - chunk.date).days
                score *= 1.2 if age < 0 else 1 + 0.6 * math.exp(-age / 30)  # future events: small boost only
            scored.append((score, chunk))

    scored.sort(key=lambda x: (-x[0], x[1].rel, x[1].line_start))

    # Show a spread of notes, not many pieces of the same file.
    picked = _spread(scored, len(scored), per_file)

    found_terms = set()
    for d in docs:
        found_terms.update(d)
    missing = [
        w for w in keywords(question)
        if not w.isdigit() and stem(w.lower()) not in found_terms
    ]
    return picked[:top_k], missing
