#!/usr/bin/env bash
# Prod deploy — run ON the prod host from the repo root: ./deploy.sh
# Flow: push from dev to GitHub, then pull + rebuild + restart here.
# Local-only files (backend/.env, frontend/.env, journal.db) are git-ignored
# and never touched by the pull.
#
# First run: if the journal-backend / journal-frontend systemd units don't
# exist yet, you'll be asked whether to create and enable them (needs root).
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
BACKEND_SVC="journal-backend.service"
FRONTEND_SVC="journal-frontend.service"
# Overridable for testing (e.g. UNIT_DIR=/tmp/units ./deploy.sh).
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"

unit_exists() { # $1 = unit name
  [[ -f "$UNIT_DIR/$1" || -f "/lib/systemd/system/$1" ]] ||
    systemctl list-unit-files --type=service 2>/dev/null | grep -q "^$1"
}

env_val() { # $1=file $2=KEY $3=default — last occurrence wins
  local val=""
  if [[ -f "$1" ]]; then
    val="$(grep -E "^[[:space:]]*$2=" "$1" | tail -n1 | cut -d= -f2- | tr -d '[:space:]' || true)"
  fi
  printf '%s' "${val:-$3}"
}

write_backend_unit() {
  local port
  port="$(env_val "$ROOT/backend/.env" PORT 8000)"
  cat >"$UNIT_DIR/$BACKEND_SVC" <<EOF
[Unit]
Description=Trading Journal backend (FastAPI)
After=network.target

[Service]
Type=simple
WorkingDirectory=$ROOT/backend
ExecStart=$ROOT/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port $port
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
}

write_frontend_unit() {
  local port origin node_bin
  port="${FRONTEND_PORT:-$(env_val "$ROOT/frontend/.env" PORT 3000)}"
  origin="${ORIGIN:-$(env_val "$ROOT/frontend/.env" ORIGIN "http://127.0.0.1:$port")}"
  node_bin="$(command -v node || echo /usr/bin/node)"
  cat >"$UNIT_DIR/$FRONTEND_SVC" <<EOF
[Unit]
Description=Trading Journal frontend (SvelteKit)
After=network.target $BACKEND_SVC

[Service]
Type=simple
WorkingDirectory=$ROOT/frontend
EnvironmentFile=-$ROOT/frontend/.env
Environment=PORT=$port
Environment=ORIGIN=$origin
ExecStart=$node_bin build
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
}

BACKEND_FRESH=0
FRONTEND_FRESH=0
missing=()
unit_exists "$BACKEND_SVC" || missing+=("$BACKEND_SVC")
unit_exists "$FRONTEND_SVC" || missing+=("$FRONTEND_SVC")

if ((${#missing[@]} > 0)); then
  echo "First run: missing systemd units: ${missing[*]}"
  answer=""
  if [[ -t 0 ]]; then
    read -r -p "Create and enable them now? [y/N] " answer || true
  else
    echo "Non-interactive shell — skipping unit creation (re-run in a terminal to create them)."
  fi
  if [[ "$answer" =~ ^[Yy]([Ee][Ss])?$ ]]; then
    if [[ "$EUID" -ne 0 && "$UNIT_DIR" == "/etc/systemd/system" ]]; then
      echo "ERROR: creating units needs root — re-run with sudo." >&2
    else
      if ! unit_exists "$BACKEND_SVC"; then write_backend_unit; BACKEND_FRESH=1; fi
      if ! unit_exists "$FRONTEND_SVC"; then write_frontend_unit; FRONTEND_FRESH=1; fi
      if [[ "$UNIT_DIR" == "/etc/systemd/system" ]]; then systemctl daemon-reload; fi
      echo "Units written to $UNIT_DIR."
    fi
  fi
fi

git pull --ff-only origin main
CHANGED="$(git diff --name-only HEAD@{1} HEAD 2>/dev/null || git ls-files)"

backend_changed=0
frontend_changed=0
if grep -q "^backend/" <<<"$CHANGED"; then backend_changed=1; fi
if grep -q "^frontend/" <<<"$CHANGED"; then frontend_changed=1; fi

if (( backend_changed || BACKEND_FRESH )); then
  if [[ ! -x backend/venv/bin/uvicorn ]]; then
    echo "Creating backend venv…"
    python3 -m venv backend/venv
  fi
  ./backend/venv/bin/pip install -q -r backend/requirements.txt
  if (( BACKEND_FRESH )); then
    systemctl enable --now "$BACKEND_SVC"
  else
    systemctl restart "$BACKEND_SVC"
  fi
fi
if (( frontend_changed || FRONTEND_FRESH )); then
  (cd frontend && npm install --no-audit --no-fund -q && npm run build)
  if (( FRONTEND_FRESH )); then
    systemctl enable --now "$FRONTEND_SVC"
  else
    systemctl restart "$FRONTEND_SVC"
  fi
fi

for svc in "$BACKEND_SVC" "$FRONTEND_SVC"; do
  if unit_exists "$svc"; then
    systemctl is-active "$svc"
  else
    echo "$svc: not installed"
  fi
done
