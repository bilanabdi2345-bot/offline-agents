"""The coordinator: the only part that every agent can reach.

It does four jobs:
1. Takes tasks from you and passes each one to the right agent.
2. Asks the local model on behalf of agents (agents never reach the model).
3. Passes messages between agents, but only if policy.json allows it.
4. Writes every message to a log file so you can check what happened.

It uses only the Python standard library, so nothing needs downloading.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8000"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
MODEL = os.environ.get("MODEL", "llama3.2:3b")
FAKE_LLM = os.environ.get("FAKE_LLM") == "1"
LOG_FILE = os.environ.get("LOG_FILE", "/logs/messages.jsonl")
POLICY_FILE = os.environ.get(
    "POLICY_FILE", os.path.join(os.path.dirname(__file__), "policy.json")
)
MAX_DEPTH = int(os.environ.get("MAX_DEPTH", "3"))
TIMEOUT = int(os.environ.get("TIMEOUT", "300"))


def parse_agents(text):
    """Read 'agent_a=http://agent_a:9000,agent_b=...' into a dict."""
    agents = {}
    for part in text.split(","):
        part = part.strip()
        if part:
            name, url = part.split("=", 1)
            agents[name.strip()] = url.strip()
    return agents


AGENTS = parse_agents(
    os.environ.get(
        "AGENTS",
        "agent_a=http://agent_a:9000,agent_b=http://agent_b:9000,agent_c=http://agent_c:9000",
    )
)

# Each agent has a secret token. The token tells the coordinator who is asking.
TOKENS = {}
for _name in AGENTS:
    _token = os.environ.get(f"TOKEN_{_name.upper()}")
    if _token:
        TOKENS[_token] = _name

with open(POLICY_FILE) as f:
    POLICY = json.load(f)

_log_lock = threading.Lock()


def log(event, **data):
    record = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **data}
    line = json.dumps(record)
    print(line, flush=True)
    folder = os.path.dirname(LOG_FILE)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with _log_lock, open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def post_json(url, payload, headers=None):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def ask_model(messages):
    """Send a chat to the local model and return its reply text."""
    if FAKE_LLM:
        last = messages[-1]["content"]
        # The fake model lets the tests check agent-to-agent messages.
        for target in AGENTS:
            if f"please ask {target}" in last.lower():
                return f"ASK {target}: hello from the test"
        return f"Fake model reply to: {last[-80:]}"
    result = post_json(
        f"{OLLAMA_URL}/api/chat",
        {"model": MODEL, "messages": messages, "stream": False},
    )
    return result["message"]["content"]


def can_message(sender, target):
    return target in POLICY.get(sender, {}).get("can_message", [])


def send_to_agent(agent, message, depth, sender="user"):
    url = AGENTS[agent]
    return post_json(
        f"{url}/work", {"message": message, "from": sender, "depth": depth}
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # We keep our own log instead.

    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def caller(self):
        """Work out which agent is calling, from its token."""
        return TOKENS.get(self.headers.get("X-Agent-Token", ""))

    def do_GET(self):
        if self.path == "/health":
            return self.reply(200, {"ok": True, "agents": list(AGENTS)})
        self.reply(404, {"error": "not found"})

    def do_POST(self):
        try:
            data = self.read_body()
        except json.JSONDecodeError:
            return self.reply(400, {"error": "bad JSON"})

        try:
            if self.path == "/task":
                return self.handle_task(data)
            if self.path == "/llm":
                return self.handle_llm(data)
            if self.path == "/send":
                return self.handle_send(data)
            self.reply(404, {"error": "not found"})
        except urllib.error.URLError as e:
            log("error", path=self.path, detail=str(e))
            self.reply(502, {"error": f"could not reach a service: {e}"})

    # You -> coordinator -> agent
    def handle_task(self, data):
        agent = data.get("agent")
        message = data.get("message", "")
        if agent not in AGENTS:
            return self.reply(400, {"error": f"unknown agent: {agent}"})
        log("task", to=agent, message=message)
        result = send_to_agent(agent, message, depth=0)
        log("task_done", agent=agent, reply=result.get("reply"))
        self.reply(200, result)

    # Agent -> coordinator -> model
    def handle_llm(self, data):
        agent = self.caller()
        if not agent:
            log("blocked", reason="bad token", path="/llm")
            return self.reply(403, {"error": "unknown agent token"})
        messages = data.get("messages", [])
        log("model_call", agent=agent, last=messages[-1]["content"] if messages else "")
        text = ask_model(messages)
        log("model_reply", agent=agent, reply=text)
        self.reply(200, {"reply": text})

    # Agent -> coordinator -> another agent
    def handle_send(self, data):
        sender = self.caller()
        if not sender:
            log("blocked", reason="bad token", path="/send")
            return self.reply(403, {"error": "unknown agent token"})
        target = data.get("to")
        depth = int(data.get("depth", 0)) + 1
        if target not in AGENTS:
            return self.reply(400, {"error": f"unknown agent: {target}"})
        if not can_message(sender, target):
            log("blocked", reason="policy", sender=sender, target=target)
            return self.reply(403, {"error": f"{sender} may not message {target}"})
        if depth > MAX_DEPTH:
            log("blocked", reason="too deep", sender=sender, target=target)
            return self.reply(429, {"error": "too many hops between agents"})
        message = data.get("message", "")
        log("agent_message", sender=sender, to=target, message=message)
        result = send_to_agent(target, message, depth=depth, sender=sender)
        self.reply(200, result)


def main():
    log("start", port=PORT, agents=list(AGENTS), fake_model=FAKE_LLM)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
