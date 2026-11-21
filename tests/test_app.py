"""Tests for the chat app server. No Docker needed."""

import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class AppServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.url = f"http://127.0.0.1:{cls.port}"
        env = dict(os.environ, FAKE_ASK="1", APP_PORT=str(cls.port))
        cls.proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "app", "server.py")], env=env)
        for _ in range(50):
            try:
                urllib.request.urlopen(cls.url, timeout=1)
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait()

    def post(self, path, payload, headers=None):
        h = {"Content-Type": "application/json", "X-Offline-Agents": "1", **(headers or {})}
        req = urllib.request.Request(self.url + path, data=json.dumps(payload).encode(), headers=h)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def test_page_loads(self):
        html = urllib.request.urlopen(self.url).read().decode()
        self.assertIn("Offline Agents", html)

    def test_ask_works(self):
        result = self.post("/ask", {"agent": "agent_b", "message": "check this"})
        self.assertIn("agent_b got: check this", result["reply"])

    def test_unknown_agent_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/ask", {"agent": "agent_z", "message": "hi"})
        self.assertEqual(ctx.exception.code, 400)

    def test_other_websites_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/ask", {"agent": "agent_a", "message": "hi"}, {"Origin": "https://evil.example"})
        self.assertEqual(ctx.exception.code, 403)

    def test_missing_header_blocked(self):
        req = urllib.request.Request(
            self.url + "/ask",
            data=b'{"agent":"agent_a","message":"hi"}',
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
