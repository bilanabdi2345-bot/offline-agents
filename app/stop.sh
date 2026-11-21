#!/bin/bash
# Stops the agents and the chat app server.
cd "$(dirname "$0")/.."
docker compose down
pkill -f "app/server.py" && echo "Chat app stopped." || true
