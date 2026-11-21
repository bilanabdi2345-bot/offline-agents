"""Tests for Second Brain. No AI model needed: they use a fake one.

Run:  python3 -B -m unittest discover tests
"""

import datetime as dt
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
sys.path.insert(0, ROOT)
os.environ["FAKE_LLM"] = "1"
os.environ["TODAY"] = "2026-11-22"

from secondbrain import brain, notes, search  # noqa: E402

DAY = dt.date(2026, 11, 22)
SAMPLE = os.path.join(ROOT, "sample-notes")


def comps(personal=False):
    return brain.Compartments([
        {"name": "Team", "path": os.path.join(SAMPLE, "Team"), "enabled": True},
        {"name": "Projects", "path": os.path.join(SAMPLE, "Projects"), "enabled": True},
        {"name": "Personal", "path": os.path.join(SAMPLE, "Personal"), "enabled": personal},
    ])


class ReadingNotes(unittest.TestCase):
    def test_reads_every_kind(self):
        chunks, files = notes.read_compartment("Projects", os.path.join(SAMPLE, "Projects"), DAY)
        kinds = {c.kind for c in chunks}
        self.assertEqual(kinds, {"note", "action list", "calendar", "saved link"})
        self.assertIn("Projects/action-items.csv", files)

    def test_messy_dates(self):
        self.assertEqual(notes.find_date("1:1 priya 2 nov", DAY), dt.date(2026, 11, 2))
        self.assertEqual(notes.find_date("standup 4/11 - marcus", DAY), dt.date(2026, 11, 4))
        self.assertEqual(notes.find_date("2026-10-20 Steering group.md", DAY), dt.date(2026, 10, 20))
        self.assertEqual(notes.find_date("DTSTART:20261123T100000", DAY), dt.date(2026, 11, 23))
        self.assertIsNone(notes.find_date("no date here", DAY))
        self.assertEqual(notes.find_date("standup 16/11 - priya thinks done by 27 nov", DAY), dt.date(2026, 11, 16))

    def test_flags(self):
        chunks, _ = notes.read_compartment("Projects", os.path.join(SAMPLE, "Projects"), DAY)
        draft = [c for c in chunks if "draft" in c.rel]
        self.assertIn("unfinished draft", draft[0].flags)
        overdue = [c for c in chunks if "overdue" in c.flags]
        self.assertTrue(any("QA triage" in c.text for c in overdue))
        done = [c for c in chunks if "status: done" in c.text]
        self.assertTrue(all("overdue" not in c.flags for c in done))


class Searching(unittest.TestCase):
    def setUp(self):
        self.chunks = []
        for name in ("Team", "Projects"):
            c, _ = notes.read_compartment(name, os.path.join(SAMPLE, name), DAY)
            self.chunks += c

    def test_finds_newer_decision(self):
        hits, _ = search.search("When is the patient app launching?", self.chunks, today=DAY)
        files = [c.rel for _, c in hits]
        self.assertIn("Projects/2026-10-20 Steering group.md", files)

    def test_finds_overdue_by_flag(self):
        hits, _ = search.search("What actions are overdue?", self.chunks, today=DAY)
        self.assertIn("overdue", hits[0][1].flags)

    def test_reports_missing_words(self):
        _, missing = search.search("What did we decide about the Lagos budget?", self.chunks, today=DAY)
        self.assertIn("Lagos", missing)


class Answering(unittest.TestCase):
    def test_switched_off_folder_is_never_read(self):
        r = brain.answer("reorg", comps(personal=False))
        self.assertFalse(any(f.startswith("Personal") for f in r["files_read"]))
        self.assertIn("Personal", r["skipped"])
        self.assertFalse(r["found"])

    def test_switched_on_folder_is_read(self):
        r = brain.answer("reorg", comps(personal=True))
        self.assertTrue(r["found"])

    def test_honest_when_not_found(self):
        r = brain.answer("xylophone quarterly", comps())
        self.assertFalse(r["found"])
        self.assertIn("couldn't find", r["answer"])
        self.assertEqual(r["sources"], [])

    def test_sources_and_explanation(self):
        r = brain.answer("What did Marcus say about QA?", comps())
        self.assertTrue(r["found"])
        self.assertTrue(r["sources"])
        self.assertIn("I kept no copy", r["explanation"])

    def test_next_meeting(self):
        m = brain.meeting_question(comps())
        self.assertEqual(m["title"], "1:1 with Priya")


class Guards(unittest.TestCase):
    """Run in a separate process so the guards don't affect other tests."""

    def run_py(self, code):
        return subprocess.run(
            [sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=30
        )

    def test_network_and_writes_blocked(self):
        code = (
            "from secondbrain import guards; guards.install()\n"
            "r = guards.try_to_leak()\n"
            "print(all(x['blocked'] for x in r), len(r))\n"
            "import os; print(os.path.exists('copy-of-your-notes.txt'))\n"
        )
        out = self.run_py(code).stdout.split()
        self.assertEqual(out, ["True", "3", "False"])

    def test_local_still_allowed(self):
        code = (
            "import socket\n"
            "srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)\n"
            "port = srv.getsockname()[1]\n"
            "from secondbrain import guards; guards.install()\n"
            "socket.create_connection(('127.0.0.1', port), timeout=2).close()\n"
            "print('ok', guards.report()['allowed_connections'])\n"
        )
        result = self.run_py(code)
        self.assertTrue(result.stdout.startswith("ok"), result.stderr)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port()
        cls.url = f"http://127.0.0.1:{cls.port}"
        env = dict(os.environ, PORT=str(cls.port))
        cls.proc = subprocess.Popen(
            [sys.executable, "-B", "-m", "secondbrain", "--no-browser"], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(60):
            try:
                urllib.request.urlopen(cls.url, timeout=1)
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait()

    def call(self, path, body=None, headers=None):
        h = {"Content-Type": "application/json", "X-Second-Brain": "1", **(headers or {})}
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, headers=h)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def test_page_and_state(self):
        html = urllib.request.urlopen(self.url).read().decode()
        self.assertIn("Second Brain", html)
        s = self.call("/api/state")
        self.assertEqual([c["name"] for c in s["compartments"]], ["Team", "Projects", "Personal"])

    def test_ask_and_trust(self):
        r = self.call("/api/ask", {"question": "When is the patient app launching?"})
        self.assertTrue(r["found"])
        t = self.call("/api/trust")
        self.assertTrue(t["guards_on"])
        self.assertTrue(t["notes"]["unchanged"])
        self.assertEqual(t["writes"]["files_written"], 0)

    def test_toggle_changes_what_is_read(self):
        self.call("/api/compartment", {"action": "toggle", "name": "Personal", "enabled": True})
        r = self.call("/api/ask", {"question": "reorg"})
        self.assertTrue(any(f.startswith("Personal") for f in r["files_read"]))
        self.call("/api/compartment", {"action": "toggle", "name": "Personal", "enabled": False})
        r = self.call("/api/ask", {"question": "reorg"})
        self.assertFalse(any(f.startswith("Personal") for f in r["files_read"]))

    def test_try_to_leak_is_blocked(self):
        r = self.call("/api/try-to-leak", {})
        self.assertTrue(all(x["blocked"] for x in r["results"]))

    def test_other_websites_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("/api/state", headers={"Origin": "https://evil.example"})
        self.assertEqual(ctx.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.call("/api/state", headers={"Host": "evil.example"})
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
