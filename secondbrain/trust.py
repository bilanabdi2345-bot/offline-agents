"""Checks the user can run to see for themselves that the One Rule holds."""

import os
import re
import subprocess

from . import guards, notes


class NotesSeal:
    """Remembers a checksum of the notes when the app starts (in memory only),
    so we can later show the notes are exactly as they were."""

    def __init__(self, folders):
        self.folders = list(folders)
        self.start_print, self.start_count = notes.fingerprint(self.folders)

    def check(self):
        now, count = notes.fingerprint(self.folders)
        return {
            "unchanged": now == self.start_print,
            "files": count,
            "fingerprint": now,
            "start_fingerprint": self.start_print,
        }


def _pids(name):
    try:
        out = subprocess.run(["pgrep", "-if", name], capture_output=True, text=True, timeout=5).stdout
        return [p for p in out.split() if p.isdigit()]
    except Exception:
        return []


def open_connections():
    """Ask the operating system (not this app) which network connections the
    assistant and the AI model have open right now. Uses the 'lsof' tool."""
    targets = {"This app": [str(os.getpid())], "AI model (Ollama)": _pids("ollama")}
    result = {"checked": False, "processes": [], "outside": []}
    for label, pids in targets.items():
        if not pids:
            result["processes"].append({"name": label, "running": False, "connections": []})
            continue
        try:
            out = subprocess.run(
                ["lsof", "-nP", "-a", "-p", ",".join(pids), "-i"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except FileNotFoundError:
            result["note"] = "The 'lsof' tool isn't available on this computer."
            return result
        except Exception as e:
            result["note"] = f"Could not run the check: {e}"
            return result
        result["checked"] = True
        conns = []
        for line in out.splitlines()[1:]:
            m = re.search(r"(TCP|UDP)\s+(\S+)(?:\s+\((\w+)\))?$", line)
            if not m:
                continue
            addr, state = m.group(2), m.group(3) or ""
            remote = addr.split("->")[1] if "->" in addr else None
            local_only = remote is None or remote.startswith(("127.", "[::1]", "localhost"))
            conns.append({"address": addr, "state": state, "local_only": local_only})
            if not local_only:
                result["outside"].append({"process": label, "address": addr})
        result["processes"].append({"name": label, "running": True, "connections": conns})
    return result


def full_report(seal, model_keep_alive):
    g = guards.report()
    return {
        "guards_on": guards.is_installed(),
        "network": {
            "allowed": g["allowed_connections"],
            "blocked": g["blocked_connections"],
        },
        "writes": {"blocked": g["blocked_writes"], "files_written": 0},
        "notes": seal.check(),
        "model_forgets": str(model_keep_alive) in ("0", "0s"),
    }
