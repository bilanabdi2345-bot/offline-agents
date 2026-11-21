"""One agent. The same code runs in every agent box.

Each agent:
- has its own role (set by the ROLE setting),
- keeps its own private notes in /notes (no other agent can see them),
- can only talk to the coordinator.

To ask another agent for help, the model writes a line like:
    ASK agent_b: <question>
The agent passes that to the coordinator, which checks policy.json first.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NAME = os.environ.get("AGENT_NAME", "agent")
ROLE = os.environ.get("ROLE", "You are a helpful assistant.")
PORT = int(os.environ.get("PORT", "9000"))
COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8000")
TOKEN = os.environ.get("AGENT_TOKEN", "")
NOTES_DIR = os.environ.get("NOTES_DIR", "/notes")
NOTES_FILE = os.path.join(NOTES_DIR, "notes.md")
MAX_NOTE_CHARS = int(os.environ.get("MAX_NOTE_CHARS", "4000"))
TIMEOUT = int(os.environ.get("TIMEOUT", "300"))

ASK_PATTERN = re.compile(r"^ASK\s+(\w+):\s*(.+)$", re.MULTILINE)

SYSTEM_PROMPT = f"""{ROLE}

You are {NAME}. You work inside a private, offline box.
Your private notes are shown below. Only you can see them.
If you need help from another agent, write one line exactly like this:
ASK <agent_name>: <your question>
You may only ask agents you are allowed to ask. Otherwise, just answer."""


def call_coordinator(path, payload):
    req = urllib.request.Request(
        f"{COORDINATOR_URL}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Agent-Token": TOKEN},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def read_notes():
    try:
        with open(NOTES_FILE) as f:
            return f.read()[-MAX_NOTE_CHARS:]
    except FileNotFoundError:
        return ""


def add_note(sender, message, reply):
    os.makedirs(NOTES_DIR, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    with open(NOTES_FILE, "a") as f:
        f.write(f"\n## {stamp} from {sender}\nTask: {message}\nAnswer: {reply}\n")


def think(message, sender, depth):
    notes = read_notes() or "(no notes yet)"
    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\nYOUR NOTES:\n{notes}"},
        {"role": "user", "content": f"Message from {sender}: {message}"},
    ]
    reply = call_coordinator("/llm", {"messages": messages})["reply"]

    # If the model wants help from another agent, ask once via the coordinator.
    match = ASK_PATTERN.search(reply)
    if match:
        target, question = match.group(1), match.group(2)
        try:
            answer = call_coordinator(
                "/send", {"to": target, "message": question, "depth": depth}
            )["reply"]
        except urllib.error.HTTPError as e:
            answer = f"(not allowed or failed: {e.read().decode()})"
        messages += [
            {"role": "assistant", "content": reply},
            {
                "role": "user",
                "content": f"Reply from {target}: {answer}\nNow give your final answer. Do not ASK again.",
            },
        ]
        reply = call_coordinator("/llm", {"messages": messages})["reply"]

    add_note(sender, message, reply)
    return reply


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"ok": True, "agent": NAME})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/work":
            return self.reply(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length) or b"{}")
        try:
            text = think(
                data.get("message", ""), data.get("from", "user"), int(data.get("depth", 0))
            )
            self.reply(200, {"agent": NAME, "reply": text})
        except urllib.error.URLError as e:
            self.reply(502, {"agent": NAME, "error": str(e)})


def main():
    print(f"{NAME} listening on port {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
