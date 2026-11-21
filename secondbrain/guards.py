"""Two guards that enforce the One Rule inside this program.

1. Network guard: this program may only talk to this laptop (127.0.0.1).
   Any attempt to reach anything else, including a DNS lookup, is blocked
   and recorded so the user can see it.

2. Write guard: this program may not write any file. It has no database,
   no index, no cache and no log file. So it cannot keep a copy of your notes.

Both guards are switched on before anything else runs (see __main__.py).
"""

import builtins
import io
import os
import socket
import threading
import time

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}

_lock = threading.Lock()
_events = {
    "allowed_connections": {},  # "127.0.0.1:11434" -> count
    "blocked_connections": [],  # list of {"time", "target"}
    "blocked_writes": [],  # list of {"time", "path"}
}
_installed = False


def _now():
    return time.strftime("%H:%M:%S")


def _record_blocked(kind, detail):
    with _lock:
        _events[kind].append({"time": _now(), "target": str(detail)})


def _is_local(host):
    host = str(host).strip("[]").lower()
    return host in LOCAL_HOSTS or host.startswith("127.")


class BlockedByOneRule(PermissionError):
    pass


def install():
    """Switch both guards on. Safe to call more than once."""
    global _installed
    if _installed:
        return
    _installed = True

    # --- Network guard ---
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def check(address):
        if isinstance(address, tuple):
            host, port = address[0], address[1]
            target = f"{host}:{port}"
            if not _is_local(host):
                _record_blocked("blocked_connections", target)
                raise BlockedByOneRule(f"Blocked: tried to reach {target} (not this laptop)")
            with _lock:
                _events["allowed_connections"][target] = (
                    _events["allowed_connections"].get(target, 0) + 1
                )
        # Unix sockets (strings) stay on this machine, so they are allowed.

    def guarded_connect(self, address):
        check(address)
        return real_connect(self, address)

    def guarded_connect_ex(self, address):
        check(address)
        return real_connect_ex(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host is not None and not _is_local(host if isinstance(host, str) else host.decode()):
            _record_blocked("blocked_connections", f"DNS lookup for {host}")
            raise BlockedByOneRule(f"Blocked: tried to look up {host} (not this laptop)")
        return real_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex
    socket.getaddrinfo = guarded_getaddrinfo

    # --- Write guard ---
    real_open = builtins.open
    real_os_open = os.open
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(c in mode for c in "wax+") and not isinstance(file, int):
            _record_blocked("blocked_writes", file)
            raise BlockedByOneRule(f"Blocked: tried to write {file}")
        return real_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & write_flags:
            _record_blocked("blocked_writes", path)
            raise BlockedByOneRule(f"Blocked: tried to write {path}")
        return real_os_open(path, flags, *args, **kwargs)

    builtins.open = guarded_open
    io.open = guarded_open
    os.open = guarded_os_open


def is_installed():
    return _installed


def report():
    with _lock:
        return {
            "allowed_connections": dict(_events["allowed_connections"]),
            "blocked_connections": list(_events["blocked_connections"]),
            "blocked_writes": list(_events["blocked_writes"]),
        }


def try_to_leak():
    """Deliberately try to reach the internet and write a file, so the user
    can watch both guards block it."""
    if not _installed:
        return [{"test": "Guards are not switched on", "blocked": False}]
    results = []
    try:
        socket.create_connection(("example.com", 443), timeout=3).close()
        results.append({"test": "Reach the internet (example.com)", "blocked": False})
    except BlockedByOneRule:
        results.append({"test": "Reach the internet (example.com)", "blocked": True})
    except OSError:
        results.append({"test": "Reach the internet (example.com)", "blocked": True})
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3).close()
        results.append({"test": "Reach an outside server (8.8.8.8)", "blocked": False})
    except BlockedByOneRule:
        results.append({"test": "Reach an outside server (8.8.8.8)", "blocked": True})
    except OSError:
        results.append({"test": "Reach an outside server (8.8.8.8)", "blocked": True})
    try:
        with open("copy-of-your-notes.txt", "w") as f:
            f.write("this should never happen")
        results.append({"test": "Save a copy of your notes to disk", "blocked": False})
    except BlockedByOneRule:
        results.append({"test": "Save a copy of your notes to disk", "blocked": True})
    return results
