#!/bin/sh
# One-time setup. Run this while you still have internet.
# 1. Makes secret tokens for each agent (saved in .env, never shared).
# 2. Downloads the model into a local Docker volume.
# 3. Builds the boxes.
set -e
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Making secret tokens in .env ..."
  {
    echo "MODEL=llama3.2:3b"
    for a in A B C; do
      echo "AGENT_${a}_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
    done
  } > .env
fi

echo "Downloading the model (this can take a while) ..."
docker compose --profile setup run --rm model-download

echo "Building the boxes ..."
docker compose build

echo
echo "Setup done. You can now turn the internet off and run:"
echo "  docker compose up -d"
