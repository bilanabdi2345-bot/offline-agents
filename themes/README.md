# Themes

Drop a theme file (`.json`) in this folder and it appears in **Appearance → Theme gallery**.
You can also import a theme file straight from the app, or make your own there and download it.

A theme can only hold colours, a font choice, corner roundness and light/dark.
No code and no web addresses, so a theme from anywhere is safe to use.

```json
{
  "name": "Forest",
  "author": "Your name",
  "mode": "dark",
  "colors": {
    "accent": "#3fae7a",
    "background": "#14201a",
    "panel": "#1b2a22",
    "text": "#e8f1ea",
    "muted": "#9db5a6",
    "line": "#2c4035"
  },
  "font": "rounded",
  "radius": 18
}
```

- **mode**: `light` or `dark` (sets warning colours to match)
- **colors**: six colours, each like `#12ab34`
- **font**: `system`, `serif`, `rounded`, `mono` or `verdana`
- **radius**: 0 (sharp) to 28 (very round)

Made a theme you like? Share the file, or open a pull request adding it to this folder.
