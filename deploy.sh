#!/bin/bash
# Usage: ./deploy.sh
# Run on VPS to pull latest code and rebuild/restart containers.
set -e

echo "=== Pulling latest code ==="
git pull origin master

echo "=== Rebuilding images ==="
docker compose build --no-cache

echo "=== Restarting services ==="
docker compose up -d

echo "=== Done. Waiting for backend to start... ==="
sleep 5
docker compose ps
