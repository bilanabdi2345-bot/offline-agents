"""Finds the pieces of notes that match a question.

It scores every piece fresh for each question, in memory (BM25 scoring).
No search index is built or saved, because an index would be a copy.
"""

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
    jan feb mar apr jun jul aug sep sept oct nov dec""".split()
)
# Words like "decision" are in STOP for matching, but we still use them to
# give a small boost to pieces that record decisions.
BOOSTS = {
    "decision": ("decision", "decided", "agreed", "moved"),
    "action": ("action", "todo", "follow up", "status: open"),
}


def stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokens(text):
    words = re.findall(r"[a-z0-9]+(?::[0-9]+)?", text.lower())
    return [stem(w) for w in words if w not in STOP and len(w) > 1]


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


def search(question, chunks, top_k=10, k1=1.4, b=0.75, per_file=2, today=None):
    """Return (best pieces with scores, keywords not found anywhere)."""
    q = tokens(question)
    if not q or not chunks:
        return [], keywords(question)

    docs = [tokens(c.text + " " + c.rel + " " + " ".join(c.flags)) for c in chunks]
    n = len(docs)
    avg = sum(len(d) for d in docs) / n or 1
    df = Counter()
    for d in docs:
        df.update(set(d))

    ql = question.lower()
    wants = [k for k, words in BOOSTS.items() if k in ql or any(w in ql for w in words)]

    scored = []
    for chunk, d in zip(chunks, docs):
        tf = Counter(d)
        score = 0.0
        for term in set(q):
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(d) / avg))
        if score > 0:
            text = chunk.text.lower()
            for k in wants:
                if any(w in text for w in BOOSTS[k]):
                    score *= 1.3
            # Newer notes matter more: things change, decisions get reversed.
            if today and chunk.date:
                age = max(0, (today - chunk.date).days)
                score *= 1 + 0.6 * math.exp(-age / 30)
            scored.append((score, chunk))

    scored.sort(key=lambda x: (-x[0], x[1].rel, x[1].line_start))

    # Show a spread of notes, not many pieces of the same file.
    picked, per = [], Counter()
    for s, c in scored:
        limit = per_file if c.kind == "note" else 4  # action lists and calendars hold many small items
        if per[c.rel] < limit:
            picked.append((s, c))
            per[c.rel] += 1
    scored = picked

    found_terms = set()
    for d in docs:
        found_terms.update(d)
    missing = [
        w for w in keywords(question)
        if not w.isdigit() and stem(w.lower()) not in found_terms
    ]
    return scored[:top_k], missing
