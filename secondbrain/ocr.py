"""Reads text from screenshots and photos, on this laptop only.

On a Mac it uses Apple's built-in Vision text reader, through a tiny helper
program (bin/second-brain-ocr, built from scripts/ocr.swift).
Elsewhere it uses Tesseract if installed.

The text is never saved to disk. To keep the app fast, text read from an
image is held in memory while the app is open, so each image is read once.
"Forget this session" (or closing the app) wipes it.
"""

import json
import os
import shutil
import subprocess
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAC_HELPER = os.path.join(ROOT, "bin", "second-brain-ocr")


def engine():
    if os.environ.get("FAKE_OCR") == "1":
        return "test reader"
    if os.path.exists(MAC_HELPER) and os.access(MAC_HELPER, os.X_OK):
        return "Apple Vision (built into your Mac)"
    if shutil.which("tesseract"):
        return "Tesseract"
    return None


_memory = {}  # (path, modified time, size) -> text. Memory only, never disk.
_lock = threading.Lock()


def forget():
    with _lock:
        _memory.clear()


def held_in_memory():
    with _lock:
        return len(_memory)


def read_images(paths):
    """Return {path: text}, reading each image once per session."""
    paths = list(paths)
    keys = {}
    for p in paths:
        try:
            st = os.stat(p)
            keys[p] = (p, st.st_mtime, st.st_size)
        except OSError:
            pass
    with _lock:
        known = {p: _memory[k] for p, k in keys.items() if k in _memory}
    todo = [p for p in keys if p not in known]
    if todo:
        fresh = _read(todo)
        with _lock:
            for p, text in fresh.items():
                _memory[keys[p]] = text
        known.update(fresh)
    return {p: t for p, t in known.items() if t}


def _read(paths):
    if not paths:
        return {}
    which = engine()
    if which is None:
        return {}
    if which == "test reader":
        return {p: os.environ.get("FAKE_OCR_TEXT", "Whiteboard: test text") for p in paths}
    if which.startswith("Apple"):
        try:
            out = subprocess.run(
                [MAC_HELPER, *paths], capture_output=True, text=True, timeout=120
            ).stdout
            return {r["path"]: r["text"] for r in json.loads(out or "[]") if r.get("text")}
        except Exception:
            return {}
    texts = {}
    for p in paths:
        try:
            out = subprocess.run(
                ["tesseract", p, "-", "--psm", "3"], capture_output=True, text=True, timeout=60
            ).stdout
            # Tidy: drop empty lines
            text = "\n".join(line for line in out.splitlines() if line.strip())
            if text:
                texts[p] = text
        except Exception:
            pass
    return texts
