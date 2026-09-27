#!/usr/bin/env bash
# Prod deploy — run ON the prod host from the repo root: ./deploy.sh
# Flow: push from dev to GitHub, then pull + rebuild + restart here.
# Local-only files (backend/.env, frontend/.env, journal.db) are git-ignored
# and never touched by the pull.
set -euo pipefail

cd "$(dirname "$0")"
git pull --ff-only origin main
CHANGED="$(git diff --name-only HEAD@{1} HEAD 2>/dev/null || git ls-files)"

if grep -q "^backend/" <<<"$CHANGED"; then
  ./backend/venv/bin/pip install -q -r backend/requirements.txt
  systemctl restart journal-backend.service
fi
if grep -q "^frontend/" <<<"$CHANGED"; then
  (cd frontend && npm install --no-audit --no-fund -q && npm run build)
  systemctl restart journal-frontend.service
fi
systemctl is-active journal-backend journal-frontend
