"""Choosing the local AI model, and talking to newer "thinking" models.

Codicilix works with any model installed in Ollama on this laptop. With
"model": "auto" in config.json it picks the best one you have installed that
suits your Mac's memory. You can also switch models in the app to compare.

Newer models (Qwen3, Gemma 4) can "think out loud" before answering. That is
slower and not needed here, because the code has already found the right
notes. So thinking is switched off when the model allows it, and any thinking
text that still appears is removed before it reaches the chat.

Everything here only talks to Ollama on 127.0.0.1 (this laptop).
"""

import json
import os
import re
import time
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434"
FALLBACK = "llama3.2:3b"

# Best first. "ram" is the Mac memory (GB) we'd want before choosing it.
PREFERRED = [
    {"name": "qwen3:8b", "ram": 16, "why": "best at following instructions for its size (about 5 GB)"},
    {"name": "gemma4:e4b", "ram": 24, "why": "Google's newest small model, good with documents (9.6 GB)"},
    {"name": "qwen3:4b", "ram": 8, "why": "fast and accurate on smaller Macs (about 2.5 GB)"},
    {"name": "gemma4:e2b", "ram": 16, "why": "Google's smaller model, reads pictures too (7.2 GB)"},
    {"name": "llama3.2:3b", "ram": 8, "why": "small and fast (2 GB), the model the demo was first built with"},
]

_cache = {"installed": (0, []), "caps": {}}


def ram_gb():
    try:
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return 8


def installed():
    """Models installed in Ollama on this laptop (cached for 30 seconds)."""
    t, names = _cache["installed"]
    if time.time() - t < 30 and names:
        return names
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        names = []
    _cache["installed"] = (time.time(), names)
    return names


def _is(installed_name, wanted):
    """'qwen3:8b' matches 'qwen3:8b'; 'llama3.2:3b' matches 'llama3.2:3b-instruct-q4'."""
    return installed_name == wanted or installed_name.startswith(wanted + "-") or \
        (":" not in wanted and installed_name.split(":")[0] == wanted)


def choose(configured="auto"):
    """The model to use: the configured one if it's installed, otherwise the
    best installed one that suits this Mac's memory."""
    have = installed()
    if configured and configured != "auto" and any(_is(n, configured) for n in have):
        return configured
    mem = ram_gb()
    for p in PREFERRED:
        if p["ram"] <= mem and any(_is(n, p["name"]) for n in have):
            return p["name"]
    if have:
        return have[0]
    return configured if configured and configured != "auto" else FALLBACK


def recommended():
    """What we'd suggest installing on this Mac."""
    mem = ram_gb()
    return next(p for p in PREFERRED if p["ram"] <= mem)


def describe():
    mem, have = ram_gb(), installed()
    rows = []
    for p in PREFERRED:
        rows.append({**p, "installed": any(_is(n, p["name"]) for n in have), "fits": p["ram"] <= mem})
    others = [n for n in have if not any(_is(n, p["name"]) for p in PREFERRED)]
    return {"ram_gb": mem, "models": rows, "other_installed": others, "recommended": recommended()["name"]}


def thinks(model):
    """Does this model have a thinking mode? Asked once, from Ollama itself."""
    if model in _cache["caps"]:
        return _cache["caps"][model]
    caps = []
    try:
        body = json.dumps({"model": model}).encode()
        req = urllib.request.Request(f"{OLLAMA_URL}/api/show", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            caps = json.loads(r.read()).get("capabilities", []) or []
    except Exception:
        caps = []
    _cache["caps"][model] = "thinking" in caps
    return _cache["caps"][model]


def user_text(model, prompt):
    """Qwen models also have their own 'don't think' switch, written in the message.
    Ollama's setting alone isn't always obeyed, so we send both."""
    return prompt + "\n\n/no_think" if model.lower().startswith("qwen") else prompt


REASONING_START = re.compile(r"^\s*(we are given|we have \d+ sources|okay[,.]|ok[,.] |alright|let'?s |let me |first,? (i|we|let)|"
                             r"i need to|the user (is asking|wants|asks)|to answer (this|the question))", re.I)


def looks_like_thinking(text):
    """True if a model has started 'thinking out loud' instead of answering."""
    return bool(REASONING_START.search(text[:200]))


def extras(model):
    """Extra settings for a request: no thinking, when the model allows it."""
    return {"think": False} if thinks(model) else {}


THINK_RX = re.compile(r"<think>.*?</think>|<\|channel>thought.*?<channel\|>", re.S)
OPENERS = ("<think>", "<|channel>thought")
CLOSERS = {"<think>": "</think>", "<|channel>thought": "<channel|>"}


def clean(text):
    """Remove any thinking text from a full answer."""
    return THINK_RX.sub("", text).lstrip()


def clean_stream(pieces):
    """Remove thinking text from an answer as it streams in."""
    buf, inside, started = "", None, False
    for piece in pieces:
        buf += piece
        while True:
            if inside:
                end = buf.find(CLOSERS[inside])
                if end < 0:
                    buf = buf[-30:]  # keep only enough to spot the closing tag
                    break
                buf = buf[end + len(CLOSERS[inside]):]
                inside = None
                continue
            starts = [(buf.find(o), o) for o in OPENERS if buf.find(o) >= 0]
            if starts:
                pos, opener = min(starts)
                out = buf[:pos]
                if out.strip() or started:
                    started = True
                    yield out
                buf, inside = buf[pos + len(opener):], opener
                continue
            # Hold back a few characters in case a tag is split across pieces.
            if any(o.startswith(buf[-k:]) for o in OPENERS for k in range(1, min(len(buf), 18) + 1)):
                cut = max(k for o in OPENERS for k in range(1, min(len(buf), 18) + 1) if o.startswith(buf[-k:]))
                out, buf = buf[:-cut], buf[-cut:]
            else:
                out, buf = buf, ""
            if not started:
                out = out.lstrip()
            if out:
                started = True
                yield out
            break
    if buf and not inside:
        yield buf if started else buf.lstrip()
