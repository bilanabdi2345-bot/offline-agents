"""Reads Word, Excel and PDF files, on this laptop only, including what people
wrote ON them: comments in the margin, tracked changes, sticky notes,
highlights and handwriting drawn on a PDF.

Nothing is installed and nothing is written to disk:
- Word (.docx) and Excel (.xlsx) files are zip files of text, so Python reads
  them directly, in memory.
- PDFs are read on a Mac by a tiny helper using Apple's built-in PDF reader
  (bin/second-brain-pdf, built from scripts/pdf.swift). It also reads scanned
  pages and handwriting drawn on a PDF with the Mac's own text reader.
  Elsewhere it uses pdftotext if installed, and a simple built-in reader if not.

Everything comes back as plain text, with what people wrote on the file shown
in square brackets, for example:
    [Comment by Mehreen, 11 Dec 2026, on "eval tests": Who owns these?]
"""

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import zipfile
import zlib
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_HELPER = os.path.join(ROOT, "bin", "second-brain-pdf")
MAX_PART = 30 * 1024 * 1024  # refuse "zip bombs": no single part bigger than this

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PR = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def extract(path):
    """Return the text of a Word, Excel or PDF file, or None if it can't be read."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".docx":
            return word(path)
        if ext == ".xlsx":
            return excel(path)
        if ext == ".pdf":
            return pdf(path)
    except Exception:
        return None
    return None


# ---------- shared helpers ----------

def _xml(z, name):
    """Parse one part of a Word or Excel file, safely."""
    try:
        info = z.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_PART:
        return None
    data = z.read(name)
    if b"<!DOCTYPE" in data[:2000] or b"<!ENTITY" in data:
        return None  # never expand tricky XML entities
    return ET.fromstring(data)


def _when(stamp):
    """'2026-12-11T09:30:00Z' -> '11 Dec 2026'."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", stamp or "")
    if not m:
        return ""
    try:
        d = dt.date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b %Y')}"


def _who(author, when):
    bits = [b for b in (author, when) if b]
    return " by " + ", ".join(bits) if bits else ""


def _clip(text, n=60):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------- Word ----------

def word(path):
    with zipfile.ZipFile(path) as z:
        doc = _xml(z, "word/document.xml")
        if doc is None:
            return None
        comments = {}
        croot = _xml(z, "word/comments.xml")
        if croot is not None:
            for c in croot.iter(W + "comment"):
                text = " ".join("".join(t.text or "" for t in p.iter(W + "t")) for p in c.iter(W + "p")).strip()
                comments[c.get(W + "id")] = (c.get(W + "author", ""), _when(c.get(W + "date", "")), text)

    out, open_ranges = [], {}
    body = doc.find(W + "body")
    if body is None:
        return None
    for block in body:
        rows = [block] if block.tag == W + "p" else list(block.iter(W + "p")) if block.tag == W + "tbl" else []
        for p in rows:
            line, notes, hidden = [], [], []
            # Text people can't see in Word: hidden, white, or tiny. Shown here
            # so the shield can check it, and so the manager knows it's there.
            secret = set()
            for r in p.iter(W + "r"):
                rpr = r.find(W + "rPr")
                if rpr is None:
                    continue
                color = rpr.find(W + "color")
                size = rpr.find(W + "sz")
                if (rpr.find(W + "vanish") is not None or rpr.find(W + "specVanish") is not None
                        or (color is not None and color.get(W + "val", "").upper() in ("FFFFFF", "FEFEFE"))
                        or (size is not None and size.get(W + "val", "99").isdigit() and int(size.get(W + "val")) <= 4)):
                    secret.update(r.iter(W + "t"))
            for el in p.iter():
                tag = el.tag
                if tag == W + "commentRangeStart":
                    open_ranges[el.get(W + "id")] = []
                elif tag == W + "commentRangeEnd" or tag == W + "commentReference":
                    cid = el.get(W + "id")
                    if cid in comments and cid not in [n[0] for n in notes]:
                        notes.append((cid, "".join(open_ranges.pop(cid, []))))
                elif tag == W + "t" and el.text and el in secret:
                    hidden.append(el.text)
                elif tag == W + "t" and el.text:
                    line.append(el.text)
                    for r in open_ranges.values():
                        r.append(el.text)
                elif tag == W + "delText" and el.text:
                    line.append(f" [crossed out: {el.text.strip()}] ")
                elif tag == W + "tab":
                    line.append(" ")
            # Who made the tracked changes, and when.
            changes = []
            for kind, label in ((W + "ins", "added"), (W + "del", "crossed out")):
                for ch in p.iter(kind):
                    txt = "".join(t.text or "" for t in ch.iter(W + "t" if label == "added" else W + "delText")).strip()
                    if txt:
                        changes.append(f"[Tracked change{_who(ch.get(W + 'author', ''), _when(ch.get(W + 'date', '')))}: {label} \"{_clip(txt)}\"]")
            text = re.sub(r"\s+", " ", "".join(line)).strip()
            if not text and not notes and not hidden:
                continue
            out.append(text or "(empty line)")
            if hidden:
                out.append(f"[Hidden text in the document: {' '.join(''.join(hidden).split())}]")
            out.extend(changes)
            for cid, marked in notes:
                author, when, ctext = comments[cid]
                on = f' on "{_clip(marked)}"' if marked.strip() else ""
                out.append(f"[Comment{_who(author, when)}{on}: {ctext}]")
    return _paragraphs(out)


def _paragraphs(lines):
    """Blank line between paragraphs; a paragraph's notes stay with it."""
    out = []
    for line in lines:
        if out and not line.startswith("["):
            out.append("")
        out.append(line)
    return "\n".join(out).strip() or None


# ---------- Excel ----------

def _col(ref):
    letters = re.match(r"[A-Z]+", ref or "")
    return letters[0] if letters else ""


def _rels(z, name):
    root = _xml(z, name)
    if root is None:
        return {}
    return {r.get("Id"): r for r in root.iter(PR + "Relationship")}


def _resolve(base_dir, target):
    if target.startswith("/"):
        return target.lstrip("/")
    parts = (base_dir + "/" + target).split("/")
    out = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p and p != ".":
            out.append(p)
    return "/".join(out)


def excel(path):
    with zipfile.ZipFile(path) as z:
        shared = []
        sroot = _xml(z, "xl/sharedStrings.xml")
        if sroot is not None:
            for si in sroot.iter(S + "si"):
                shared.append("".join(t.text or "" for t in si.iter(S + "t")))
        wb = _xml(z, "xl/workbook.xml")
        if wb is None:
            return None
        wrels = _rels(z, "xl/_rels/workbook.xml.rels")
        out = []
        for sheet in wb.iter(S + "sheet"):
            rel = wrels.get(sheet.get(R + "id"))
            if rel is None:
                continue
            spath = _resolve("xl", rel.get("Target"))
            root = _xml(z, spath)
            if root is None:
                continue
            # Comments on cells (the little red corner in Excel).
            notes = {}
            sdir, sfile = spath.rsplit("/", 1)
            for r in _rels(z, f"{sdir}/_rels/{sfile}.rels").values():
                if r.get("Type", "").endswith("/comments"):
                    croot = _xml(z, _resolve(sdir, r.get("Target")))
                    if croot is None:
                        continue
                    authors = [a.text or "" for a in croot.iter(S + "author")]
                    for c in croot.iter(S + "comment"):
                        i = int(c.get("authorId", "-1"))
                        who = authors[i] if 0 <= i < len(authors) else ""
                        text = "".join(t.text or "" for t in c.iter(S + "t")).strip()
                        # Excel puts "Name:" at the start of a comment; drop it.
                        if who and text.startswith(who + ":"):
                            text = text[len(who) + 1:].strip()
                        if text.startswith("[Threaded comment]"):
                            text = re.sub(r"^\[Threaded comment\].*?Comment:\s*", "", text, flags=re.S)
                        notes[c.get("ref")] = (who, text)
            hidden_sheet = sheet.get("state") in ("hidden", "veryHidden")
            out.append(f"Sheet: {sheet.get('name')}" + (" (hidden sheet)" if hidden_sheet else ""))
            for row in root.iter(S + "row"):
                cells, row_notes = [], []
                for c in row.iter(S + "c"):
                    ref, t = c.get("r"), c.get("t")
                    v = c.find(S + "v")
                    if t == "s" and v is not None:
                        val = shared[int(v.text)] if v.text and int(v.text) < len(shared) else ""
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(S + "t"))
                    else:
                        val = v.text if v is not None and v.text else ""
                    cells.append(val.strip())
                    if ref in notes:
                        who, text = notes[ref]
                        on = f" on {ref}" + (f' ("{_clip(val, 40)}")' if val.strip() else "")
                        row_notes.append(f"[Comment{_who(who, '')}{on}: {text}]")
                while cells and not cells[-1]:
                    cells.pop()
                if cells:
                    out.append(" | ".join(cells))
                out.extend(row_notes)
            out.append("")
    return "\n".join(out).strip() or None


# ---------- PDF ----------

def pdf(path):
    if os.path.exists(PDF_HELPER) and os.access(PDF_HELPER, os.X_OK):
        try:
            res = subprocess.run([PDF_HELPER, path], capture_output=True, text=True, timeout=120).stdout
            results = json.loads(res or "[]")
            if results and not results[0].get("error"):
                return _from_mac_pdf(results[0])
        except Exception:
            pass
    with open(path, "rb") as f:
        data = f.read(60 * 1024 * 1024)
    marks = _pdf_marks(data)
    text = None
    if shutil.which("pdftotext"):
        try:
            text = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True,
                                  text=True, timeout=60).stdout
            pages = [re.sub(r"\n\s*\n+", "\n", p).strip() for p in text.split("\f")]
            text = "\n\n".join(f"Page {i}\n{p}" for i, p in enumerate(pages, 1) if p)
        except Exception:
            text = None
    if not text:
        text = _pdf_text(data)
    parts = [t for t in (text, "\n".join(marks)) if t]
    return "\n\n".join(parts).strip() or None


def _from_mac_pdf(r):
    out = []
    for i, page in enumerate(r.get("pages", []), 1):
        bits = [f"Page {i}"]
        if page.get("text", "").strip():
            bits.append(page["text"].strip())
        if page.get("read_from_image", "").strip():
            bits.append("[Read from the page image]\n" + page["read_from_image"].strip())
        for n in page.get("notes", []):
            bits.append(_mark_line(n.get("type", ""), n.get("author", ""), _when(n.get("date", "")),
                                   n.get("text", ""), n.get("marked", ""), i))
        if len(bits) > 1:
            out.append("\n".join(bits))
    return "\n\n".join(out) or None


NAMES = {
    "Text": "Sticky note", "FreeText": "Note written on the page", "Highlight": "Highlighted",
    "Underline": "Underlined", "StrikeOut": "Crossed out", "Squiggly": "Underlined",
    "Ink": "Handwriting drawn on the page", "Stamp": "Stamp",
}


def _mark_line(kind, author, when, text, marked, page):
    name = NAMES.get(kind, "Note")
    who = _who(author, when)
    marked = f' "{_clip(marked, 120)}"' if marked and marked.strip() else ""
    text = f": {' '.join(text.split())}" if text and text.strip() else ""
    return f"[{name}{who}, page {page}{marked}{text}]"


# A small PDF reader for when nothing better is available. It handles PDFs
# made by everyday apps (Word, Pages, Google Docs exports); unusual fonts may
# come out empty, which is why the Mac helper is preferred.

_OBJ = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)


def _objects(data):
    objs = {}
    for m in _OBJ.finditer(data):
        objs[int(m[1])] = m[3]
    # Modern PDFs pack small objects inside compressed "object streams".
    for body in list(objs.values()):
        if b"/ObjStm" in body:
            head, stream = _split_stream(body)
            if stream is None:
                continue
            n = re.search(rb"/N\s+(\d+)", head)
            first = re.search(rb"/First\s+(\d+)", head)
            if not n or not first:
                continue
            nums = stream[: int(first[1])].split()
            pairs = [(int(nums[i]), int(nums[i + 1])) for i in range(0, min(len(nums), 2 * int(n[1])) - 1, 2)]
            for k, (num, off) in enumerate(pairs):
                start = int(first[1]) + off
                end = int(first[1]) + pairs[k + 1][1] if k + 1 < len(pairs) else len(stream)
                objs.setdefault(num, stream[start:end])
    return objs


def _split_stream(body):
    m = re.search(rb"stream\r?\n", body)
    if not m:
        return body, None
    head = body[: m.start()]
    raw = body[m.end():]
    end = raw.rfind(b"endstream")
    raw = raw[:end] if end >= 0 else raw
    if b"/FlateDecode" in head:
        try:
            raw = zlib.decompressobj().decompress(raw, MAX_PART)
        except zlib.error:
            return head, None
    elif b"/Filter" in head:
        return head, None  # images and other encodings: not text
    return head, raw


def _pdf_string(s, i):
    """Read a (literal string) starting at s[i] == '('. Returns (text, next index)."""
    out, depth, i = bytearray(), 1, i + 1
    while i < len(s) and depth:
        c = s[i]
        if c == 0x5C:  # backslash
            i += 1
            if i >= len(s):
                break
            e = s[i]
            simple = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12, 0x28: 0x28, 0x29: 0x29, 0x5C: 0x5C}
            if e in simple:
                out.append(simple[e])
            elif 0x30 <= e <= 0x37:
                oct_ = bytes([e])
                while len(oct_) < 3 and i + 1 < len(s) and 0x30 <= s[i + 1] <= 0x37:
                    i += 1
                    oct_ += bytes([s[i]])
                out.append(int(oct_, 8) & 0xFF)
            elif e in (10, 13):
                pass
            else:
                out.append(e)
        elif c == 0x28:
            depth += 1
            out.append(c)
        elif c == 0x29:
            depth -= 1
            if depth:
                out.append(c)
        else:
            out.append(c)
        i += 1
    if out[:2] == b"\xfe\xff":
        return out[2:].decode("utf-16-be", "replace"), i
    return out.decode("latin-1"), i


def _pdf_text(data):
    pages = []
    for body in _objects(data).values():
        head, stream = _split_stream(body)
        if not stream or b"BT" not in stream:
            continue
        lines, cur, i, s = [], [], 0, stream
        while i < len(s):
            c = s[i]
            if c == 0x28:
                txt, i = _pdf_string(s, i)
                cur.append(txt)
                continue
            if any(s.startswith(op, i) for op in (b"ET", b"T*", b"Td", b"TD", b"Tm", b"'")):
                if cur:
                    lines.append("".join(cur))
                    cur = []
            i += 1
        if cur:
            lines.append("".join(cur))
        text = "\n".join(l.strip() for l in lines if l.strip())
        if text and sum(ch.isprintable() for ch in text) > 0.9 * len(text):
            pages.append(text)
    return "\n\n".join(f"Page {i}\n{p}" for i, p in enumerate(pages, 1)) or None


def _pdf_marks(data):
    """Sticky notes, highlights and other marks people added to a PDF."""
    out = []
    for body in _objects(data).values():
        m = re.search(rb"/Subtype\s*/(Text|FreeText|Highlight|Underline|StrikeOut|Squiggly|Ink|Stamp)\b", body)
        if not m or b"/Annot" not in body and b"/Rect" not in body:
            continue
        def field(key):
            k = re.search(rb"/" + key + rb"\s*\(", body)
            return _pdf_string(body, k.end() - 1)[0] if k else ""
        when = field(b"M")
        dm = re.match(r"D:(\d{4})(\d{2})(\d{2})", when)
        when = _when(f"{dm[1]}-{dm[2]}-{dm[3]}") if dm else ""
        out.append(_mark_line(m[1].decode(), field(b"T"), when, field(b"Contents"), "", "?").replace(", page ?", ""))
    return out
