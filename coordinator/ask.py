"""Send a task to one agent from the command line.

Usage (from the project folder):
    docker compose exec coordinator python ask.py agent_a "Summarise what you know"
"""

import json
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("COORDINATOR_URL", "http://127.0.0.1:8000")


def main():
    if len(sys.argv) < 3:
        print('Usage: python ask.py <agent_name> "<message>"')
        sys.exit(1)
    agent, message = sys.argv[1], " ".join(sys.argv[2:])
    req = urllib.request.Request(
        f"{URL}/task",
        data=json.dumps({"agent": agent, "message": message}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            print(json.loads(resp.read()).get("reply"))
    except urllib.error.HTTPError as e:
        print("Error:", e.read().decode())
        sys.exit(1)


if __name__ == "__main__":
    main()
