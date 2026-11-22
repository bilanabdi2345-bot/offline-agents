"""Start Codicilix:  python3 -B -m secondbrain

The guards go on FIRST, before anything reads a note.
"""

import sys

sys.dont_write_bytecode = True  # don't even write Python cache files

from . import guards  # noqa: E402

guards.install()

import json  # noqa: E402
import os  # noqa: E402
import secrets  # noqa: E402
import webbrowser  # noqa: E402

from .server import serve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    path = os.environ.get("SECOND_BRAIN_CONFIG", os.path.join(ROOT, "config.json"))
    with open(path) as f:
        config = json.load(f)
    for c in config["compartments"]:
        p = os.path.expanduser(c["path"])
        c["path"] = p if os.path.isabs(p) else os.path.join(ROOT, p)
    return config


def main():
    config = load_config()
    # For the demo, pretend today is a set date (e.g. the first day back in January).
    if config.get("demo_today") and not os.environ.get("TODAY"):
        os.environ["TODAY"] = config["demo_today"]
    port = int(os.environ.get("PORT", config.get("port", 8765)))
    # A fresh secret key for this launch. Only the window we open gets it.
    token = os.environ.get("SECOND_BRAIN_TOKEN") or secrets.token_urlsafe(24)
    server, _ = serve(config, port, token)
    url = f"http://127.0.0.1:{port}/#k={token}"
    print(f"Codicilix is running at http://127.0.0.1:{port}")
    print("It only talks to this laptop. Press Ctrl+C to stop.")
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped. Nothing was saved.")


main()
