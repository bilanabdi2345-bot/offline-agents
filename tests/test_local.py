"""Tests that run without Docker and without a real model.

They start the coordinator and three agents as normal programs on this
computer, using a fake model. Run them with:
    python -m unittest discover tests
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def post(url, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def wait_for(url):
    for _ in range(50):
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"{url} did not start")


class LocalSystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.coord_port = free_port()
        cls.coord = f"http://127.0.0.1:{cls.coord_port}"
        names = ["agent_a", "agent_b", "agent_c"]
        cls.ports = {n: free_port() for n in names}
        cls.tokens = {n: f"token-{n}" for n in names}
        cls.notes = {n: os.path.join(cls.tmp, n) for n in names}

        env = dict(os.environ)
        env.update(
            PORT=str(cls.coord_port),
            FAKE_LLM="1",
            LOG_FILE=os.path.join(cls.tmp, "messages.jsonl"),
            AGENTS=",".join(f"{n}=http://127.0.0.1:{p}" for n, p in cls.ports.items()),
            **{f"TOKEN_{n.upper()}": t for n, t in cls.tokens.items()},
        )
        cls.procs = [
            subprocess.Popen([PY, os.path.join(ROOT, "coordinator", "coordinator.py")], env=env)
        ]
        for n in names:
            agent_env = dict(os.environ)
            agent_env.update(
                AGENT_NAME=n,
                PORT=str(cls.ports[n]),
                AGENT_TOKEN=cls.tokens[n],
                COORDINATOR_URL=cls.coord,
                NOTES_DIR=cls.notes[n],
            )
            cls.procs.append(
                subprocess.Popen([PY, os.path.join(ROOT, "agents", "agent.py")], env=agent_env)
            )
        wait_for(cls.coord + "/health")
        for p in cls.ports.values():
            wait_for(f"http://127.0.0.1:{p}/health")

    @classmethod
    def tearDownClass(cls):
        for p in cls.procs:
            p.terminate()
            p.wait()

    def task(self, agent, message):
        return post(self.coord + "/task", {"agent": agent, "message": message})

    def test_task_reaches_agent(self):
        result = self.task("agent_c", "hello there")
        self.assertEqual(result["agent"], "agent_c")
        self.assertIn("hello there", result["reply"])

    def test_notes_stay_private(self):
        self.task("agent_a", "secret plan for agent a only")
        with open(os.path.join(self.notes["agent_a"], "notes.md")) as f:
            self.assertIn("secret plan", f.read())
        for other in ("agent_b", "agent_c"):
            path = os.path.join(self.notes[other], "notes.md")
            if os.path.exists(path):
                with open(path) as f:
                    self.assertNotIn("secret plan", f.read())

    def test_allowed_agent_message(self):
        # policy.json lets agent_a message agent_b.
        self.task("agent_a", "please ask agent_b for help")
        log = open(os.path.join(self.tmp, "messages.jsonl")).read()
        self.assertIn('"event": "agent_message", "sender": "agent_a", "to": "agent_b"', log)

    def test_blocked_agent_message(self):
        # policy.json does NOT let agent_c message anyone.
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post(self.coord + "/send", {"to": "agent_a", "message": "hi"}, self.tokens["agent_c"])
        self.assertEqual(ctx.exception.code, 403)

    def test_bad_token_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            post(self.coord + "/llm", {"messages": [{"role": "user", "content": "x"}]}, "wrong")
        self.assertEqual(ctx.exception.code, 403)

    def test_unknown_agent_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.task("agent_z", "hi")
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
