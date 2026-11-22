"""Reads text from screenshots and photos, on this laptop only.

On a Mac it uses Apple's built-in Vision text reader, through a tiny helper
program (bin/second-brain-ocr, built from scripts/ocr.swift).
Elsewhere it uses Tesseract if installed.

Besides the text, it finds where each word sits on the picture, so the app can
let you select words on the photo and highlight the ones that matter, a bit
like Google Lens, but without anything leaving the laptop.

Nothing is saved to disk. To keep the app fast, what was read from an image is
held in memory while the app is open, so each image is read once.
"Forget this session" (or closing the app) wipes it.
"""

import json
import os
import shutil
import subprocess
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAC_HELPER = os.path.join(ROOT, "bin", "second-brain-ocr")

_memory = {}  # (path, modified time, size) -> {"text", "words", "width", "height"}. Memory only.
_lock = threading.Lock()


def engine():
    if os.environ.get("FAKE_OCR") == "1":
        return "test reader"
    if os.path.exists(MAC_HELPER) and os.access(MAC_HELPER, os.X_OK):
        return "Apple Vision (built into your Mac)"
    if shutil.which("tesseract"):
        return "Tesseract"
    return None


def forget():
    with _lock:
        _memory.clear()


def held_in_memory():
    with _lock:
        return len(_memory)


def _empty():
    return {"text": "", "words": [], "width": 0, "height": 0}


def _fake():
    return {**_empty(), "text": os.environ.get("FAKE_OCR_TEXT", "Whiteboard: test text")}


def _from_mac(results):
    out = []
    for r in results:
        out.append({
            "text": r.get("text", ""),
            "words": [{"t": w["t"], "x": w["x"], "y": w["y"], "w": w["w"], "h": w["h"]}
                      for w in r.get("words", []) if w.get("t")],
            "width": r.get("width", 0),
            "height": r.get("height", 0),
        })
    return out


def _from_tesseract_tsv(tsv):
    """Turn Tesseract's table output into text lines and word boxes (0..1)."""
    rows = [line.split("\t") for line in tsv.splitlines()]
    if not rows or len(rows[0]) < 12:
        return _empty()
    width = height = 0
    lines, words = {}, []
    for r in rows[1:]:
        if len(r) < 12:
            continue
        level = r[0]
        left, top, w, h = (int(float(v)) for v in r[6:10])
        if level == "1":
            width, height = w, h
            continue
        text = r[11].strip()
        if level != "5" or not text:
            continue
        key = (int(r[2]), int(r[3]), int(r[4]))  # block, paragraph, line
        lines.setdefault(key, []).append(text)
        words.append({"t": text, "x": left, "y": top, "w": w, "h": h})
    if width and height:
        for wd in words:
            wd["x"] /= width
            wd["w"] /= width
            wd["y"] /= height
            wd["h"] /= height
    text = "\n".join(" ".join(v) for _, v in sorted(lines.items()))
    return {"text": text, "words": words, "width": width, "height": height}


def _read_paths(paths):
    which = engine()
    if which is None:
        return {}
    if which == "test reader":
        return {p: _fake() for p in paths}
    if which.startswith("Apple"):
        try:
            out = subprocess.run([MAC_HELPER, *paths], capture_output=True, text=True, timeout=180).stdout
            results = json.loads(out or "[]")
            return {r["path"]: d for r, d in zip(results, _from_mac(results)) if d["text"]}
        except Exception:
            return {}
    found = {}
    for p in paths:
        try:
            tsv = subprocess.run(["tesseract", p, "stdout", "--psm", "3", "tsv"],
                                 capture_output=True, text=True, timeout=60).stdout
            d = _from_tesseract_tsv(tsv)
            if d["text"]:
                found[p] = d
        except Exception:
            pass
    return found


def analyse(paths):
    """Return {path: {"text", "words", "width", "height"}}, reading each image once per session."""
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
        fresh = _read_paths(todo)
        with _lock:
            for p, d in fresh.items():
                _memory[keys[p]] = d
        known.update(fresh)
    return {p: d for p, d in known.items() if d.get("text")}


def read_images(paths):
    """Return {path: text}. (Kept for the parts of the app that only need text.)"""
    return {p: d["text"] for p, d in analyse(paths).items()}


def analyse_bytes(data):
    """Read a pasted picture straight from memory. Nothing is written to disk:
    the picture is handed to the reader through a pipe."""
    which = engine()
    if which is None:
        return _empty()
    if which == "test reader":
        return _fake()
    try:
        if which.startswith("Apple"):
            out = subprocess.run([MAC_HELPER, "-"], input=data, capture_output=True, timeout=120).stdout
            results = json.loads(out.decode("utf-8") or "[]")
            return _from_mac(results)[0] if results else _empty()
        tsv = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "3", "tsv"],
                             input=data, capture_output=True, timeout=60).stdout
        return _from_tesseract_tsv(tsv.decode("utf-8", errors="replace"))
    except Exception:
        return _empty()
