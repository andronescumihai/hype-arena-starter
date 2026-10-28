#!/bin/sh
# Starts the Hype or Truth Arena frontend on http://localhost:8000
# Uses the same Docker image the organisers run (so it works offline and identically).
set -e
cd "$(dirname "$0")"
docker build --platform linux/amd64 -t hype-or-truth-arena .
echo "Open http://localhost:8000"
docker run --rm -p 8000:8000 --platform linux/amd64 hype-or-truth-arena python /app/web/server.py
