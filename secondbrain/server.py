"""The small local web server behind the app window.

It only listens on 127.0.0.1, so only this laptop can open it.
"""

import json
import os
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import brain, guards, trust

HERE = os.path.dirname(os.path.abspath(__file__))


class App:
    def __init__(self, config):
        self.config = config
        self.model = config.get("model", "llama3.2:3b")
        self.keep_alive = str(config.get("model_keep_alive", "0"))
        self.compartments = brain.Compartments(config["compartments"])
        self.seal = trust.NotesSeal(i["path"] for i in self.compartments.items)
        self.session_reads = []  # files read this session, in memory only

    def forget(self):
        self.session_reads = []


def make_handler(app, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, kind="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'")
            self.end_headers()
            self.wfile.write(data)

        def safe(self, api=True):
            # Stop other websites (and DNS tricks) from using this server.
            if self.headers.get("Host") not in allowed_hosts:
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in allowed_origins:
                return False
            return not api or self.headers.get("X-Second-Brain") == "1"

        def body(self):
            n = int(self.headers.get("Content-Length", "0") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                if not self.safe(api=False):
                    return self.send(403, {"error": "blocked"})
                with open(os.path.join(HERE, "static", "index.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if not self.safe():
                return self.send(403, {"error": "blocked"})
            day = brain.today()
            if self.path == "/api/state":
                return self.send(200, {
                    "today": day.isoformat(),
                    "compartments": app.compartments.describe(day),
                    "model": app.model,
                    "model_status": brain.model_status(app.model),
                    "next_meeting": brain.meeting_question(app.compartments),
                })
            if self.path == "/api/trust":
                report = trust.full_report(app.seal, app.keep_alive)
                report["session_reads"] = app.session_reads
                return self.send(200, report)
            self.send(404, {"error": "not found"})

        def do_POST(self):
            if not self.safe():
                return self.send(403, {"error": "blocked"})
            try:
                data = self.body()
            except json.JSONDecodeError:
                return self.send(400, {"error": "bad request"})

            if self.path == "/api/ask":
                q = (data.get("question") or "").strip()
                if not q:
                    return self.send(400, {"error": "Type a question first."})
                try:
                    result = brain.answer(q, app.compartments, app.model, app.keep_alive)
                except urllib.error.URLError:
                    return self.send(503, {"error": "The AI model isn't running. Open the Ollama app, then try again."})
                except urllib.error.HTTPError as e:
                    return self.send(503, {"error": f"The AI model had a problem: {e.read().decode()[:200]}"})
                app.session_reads.append({"question": q, "files": result["files_read"]})
                return self.send(200, result)

            if self.path == "/api/compartment":
                action = data.get("action")
                if action == "toggle":
                    ok = app.compartments.set(data.get("name"), data.get("enabled"))
                    return self.send(200 if ok else 404, {"ok": ok})
                if action == "add":
                    ok, msg = app.compartments.add(data.get("name", ""), data.get("path", ""))
                    if ok:
                        app.seal = trust.NotesSeal(i["path"] for i in app.compartments.items)
                    return self.send(200 if ok else 400, {"ok": ok, "error": msg})
                if action == "remove":
                    ok = app.compartments.remove(data.get("name"))
                    return self.send(200 if ok else 404, {"ok": ok})
                return self.send(400, {"error": "unknown action"})

            if self.path == "/api/check-connections":
                return self.send(200, trust.open_connections())

            if self.path == "/api/try-to-leak":
                return self.send(200, {"results": guards.try_to_leak()})

            if self.path == "/api/forget":
                app.forget()
                return self.send(200, {"ok": True})

            self.send(404, {"error": "not found"})

    return Handler


def serve(config, port):
    app = App(config)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, port))
    return server, app
