"""Themes: small files that change how Codicilix looks, like Obsidian themes.

A theme can ONLY hold colours, a font choice, a corner size and light/dark.
No code, no web addresses, no CSS. So a theme downloaded from anywhere can't
run anything or send anything out. Every theme is checked before it is used.

Theme file format (themes/<name>.json):
{
  "name": "Forest",
  "author": "Your name",
  "mode": "dark",                      # "light" or "dark"
  "colors": {
    "accent": "#3fae7a",               # buttons and highlights
    "background": "#14201a",           # the page
    "panel": "#1b2a22",                # cards
    "text": "#e8f1ea",
    "muted": "#9db5a6",                # quieter text
    "line": "#2c4035"                  # borders
  },
  "font": "rounded",                   # system, serif, rounded, mono, verdana
  "radius": 16                         # corner roundness, 0 to 28
}
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(ROOT, "themes")
COLOR_KEYS = ("accent", "background", "panel", "text", "muted", "line")
FONTS = ("system", "serif", "rounded", "mono", "verdana")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_BYTES = 8 * 1024


def validate(data):
    """Return (clean theme, None) or (None, reason). Unknown keys are dropped."""
    if not isinstance(data, dict):
        return None, "A theme must be a JSON object."
    name = str(data.get("name", "")).strip()[:40]
    if not name:
        return None, "The theme needs a name."
    colors = data.get("colors")
    if not isinstance(colors, dict):
        return None, "The theme needs a 'colors' section."
    clean_colors = {}
    for key in COLOR_KEYS:
        value = colors.get(key)
        if not isinstance(value, str) or not HEX.match(value):
            return None, f"Colour '{key}' must look like #12ab34."
        clean_colors[key] = value.lower()
    mode = data.get("mode", "light")
    if mode not in ("light", "dark"):
        return None, "Mode must be 'light' or 'dark'."
    font = data.get("font", "system")
    if font not in FONTS:
        return None, f"Font must be one of: {', '.join(FONTS)}."
    try:
        radius = int(data.get("radius", 14))
    except (TypeError, ValueError):
        return None, "Radius must be a number."
    radius = max(0, min(28, radius))
    author = re.sub(r"[<>\"'`]", "", str(data.get("author", "")))[:40]
    name = re.sub(r"[<>\"'`]", "", name)
    return {
        "name": name, "author": author, "mode": mode,
        "colors": clean_colors, "font": font, "radius": radius,
    }, None


def load_all():
    """Read every theme file in the themes folder. Bad files are skipped."""
    out, problems = [], []
    if not os.path.isdir(THEMES_DIR):
        return out, problems
    for fname in sorted(os.listdir(THEMES_DIR)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(THEMES_DIR, fname)
        try:
            if os.path.getsize(path) > MAX_BYTES:
                problems.append(f"{fname}: too big")
                continue
            with open(path, encoding="utf-8") as f:
                theme, err = validate(json.load(f))
        except (OSError, json.JSONDecodeError) as e:
            theme, err = None, f"couldn't read it ({e.__class__.__name__})"
        if theme:
            theme["file"] = fname
            out.append(theme)
        else:
            problems.append(f"{fname}: {err}")
    return out, problems
