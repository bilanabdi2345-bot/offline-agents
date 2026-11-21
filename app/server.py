"""The chat app's small server. It runs on your laptop, not in Docker.

It shows the chat page and passes your messages to the coordinator,
using the same command you would type in the terminal:
    docker compose exec coordinator python ask.py <agent> "<message>"

So the walls stay closed: the agents still have no internet and no new doors.

It only listens on 127.0.0.1, so only your own laptop can use it.

Start it with:
    python3 app/server.py
Then open http://127.0.0.1:8765
"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
PORT = int(os.environ.get("APP_PORT", "8765"))
FAKE = os.environ.get("FAKE_ASK") == "1"  # used by the tests
AGENTS = {"agent_a", "agent_b", "agent_c"}
ALLOWED_ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}


def run(cmd, timeout=600):
    result = subprocess.run(
        cmd, cwd=PROJECT, capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def ask(agent, message):
    if FAKE:
        return 0, f"(test) {agent} got: {message}"
    return run(
        ["docker", "compose", "exec", "-T", "coordinator", "python", "ask.py", agent, message]
    )


def agents_running():
    if FAKE:
        return True
    code, out = run(["docker", "compose", "ps", "--services", "--status", "running"], 30)
    return code == 0 and "coordinator" in out.split()


def start_agents():
    if FAKE:
        return 0, "started"
    return run(["docker", "compose", "up", "-d"], 300)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def safe_request(self):
        """Block other websites from using this server behind your back."""
        origin = self.headers.get("Origin")
        if origin and origin not in ALLOWED_ORIGINS:
            return False
        return self.headers.get("X-Offline-Agents") == "1"

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if self.path == "/status":
            if not self.safe_request():
                return self.send(403, {"error": "blocked"})
            return self.send(200, {"running": agents_running()})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        if not self.safe_request():
            return self.send(403, {"error": "blocked"})
        length = int(self.headers.get("Content-Length", "0"))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send(400, {"error": "bad request"})

        if self.path == "/start":
            code, out = start_agents()
            return self.send(200 if code == 0 else 500, {"ok": code == 0, "output": out})

        if self.path == "/ask":
            agent = data.get("agent")
            message = (data.get("message") or "").strip()
            if agent not in AGENTS:
                return self.send(400, {"error": "Pick an agent first."})
            if not message:
                return self.send(400, {"error": "Type a message first."})
            try:
                code, out = ask(agent, message)
            except subprocess.TimeoutExpired:
                return self.send(504, {"error": "The agent took too long to answer."})
            if code != 0:
                return self.send(500, {"error": out or "Something went wrong."})
            return self.send(200, {"reply": out})

        self.send(404, {"error": "not found"})


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Chat app running at http://127.0.0.1:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
