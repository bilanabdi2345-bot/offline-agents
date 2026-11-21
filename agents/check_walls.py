"""Test the walls from inside an agent box.

Run it like this, from the project folder:
    docker compose exec agent_a python check_walls.py

Every line should say PASS. A FAIL means a wall has a hole in it.
"""

import os
import socket
import urllib.request

NAME = os.environ.get("AGENT_NAME", "agent")
OTHERS = [a for a in ("agent_a", "agent_b", "agent_c") if a != NAME]
results = []


def check(label, ok):
    results.append(ok)
    print(("PASS" if ok else "FAIL"), "-", label)


def can_connect(host, port):
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


# 1. The internet must be unreachable.
check("cannot reach the internet (1.1.1.1)", not can_connect("1.1.1.1", 443))
check("cannot reach the internet (example.com)", not can_connect("example.com", 443))

# 2. Other agents must be unreachable.
for other in OTHERS:
    check(f"cannot reach {other} directly", not can_connect(other, 9000))

# 3. The model must be unreachable (only the coordinator may use it).
check("cannot reach the model directly", not can_connect("ollama", 11434))

# 4. Other agents' notes must not exist in this box.
for other in OTHERS:
    suffix = other.split("_")[-1]
    check(f"cannot see notes of {other}", not os.path.exists(f"/notes_{suffix}"))

# 5. The box itself is read-only, apart from /notes and /tmp.
try:
    open("/app/hack.txt", "w").close()
    check("app folder is read-only", False)
except OSError:
    check("app folder is read-only", True)

# 6. The coordinator must be reachable (this is the one allowed door).
try:
    urllib.request.urlopen(
        os.environ.get("COORDINATOR_URL", "http://coordinator:8000") + "/health", timeout=3
    )
    check("can reach the coordinator", True)
except OSError:
    check("can reach the coordinator", False)

print()
print("All walls hold." if all(results) else "Some walls have holes. See FAIL lines.")
