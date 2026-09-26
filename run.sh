#!/usr/bin/env bash
# Run the trading-journal app (backend + frontend) for local dev.
#
# Usage:
#   ./run.sh [options]
#
# Options:
#   --backend-only    start only the FastAPI backend
#   --frontend-only   start only the SvelteKit frontend (needs a backend URL)
#   --build           rebuild the frontend (npm run build) before starting
#   --no-build        skip the build-exists check (use current build/ as-is)
#   --install         (re)install backend + frontend dependencies first
#   -h, --help        show this help
#
# Env (all optional, sane defaults per AGENTS.md):
#   BACKEND_HOST      default 127.0.0.1
#   BACKEND_PORT      default: $PORT from backend/.env, else 8000
#   FRONTEND_PORT     default 3000
#   ORIGIN            default http://127.0.0.1:<FRONTEND_PORT>
#   PUBLIC_API_BASE   backend URL the *browser* uses (frontend build-time env).
#                     The script does NOT rewrite frontend/.env; rebuild the
#                     frontend after changing it.
#
# Paths resolve from this script's directory — no hardcoded /opt or /root.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"

RUN_BACKEND=1
RUN_FRONTEND=1
DO_BUILD=0
SKIP_BUILD_CHECK=0
DO_INSTALL=0

for arg in "$@"; do
  case "$arg" in
    --backend-only)  RUN_FRONTEND=0 ;;
    --frontend-only) RUN_BACKEND=0 ;;
    --build)         DO_BUILD=1 ;;
    --no-build)      SKIP_BUILD_CHECK=1 ;;
    --install)       DO_INSTALL=1 ;;
    -h|--help)
      sed -n '2,/^$/p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (see --help)" >&2
      exit 2
      ;;
  esac
done

# Backend port: explicit env wins, then backend/.env PORT, then 8000.
env_port_from_file() {
  # Prints PORT from backend/.env if set (ignores comments/blank lines).
  if [[ -f "$BACKEND_DIR/.env" ]]; then
    grep -E '^[[:space:]]*PORT=' "$BACKEND_DIR/.env" | tail -n1 | cut -d= -f2- | tr -d '[:space:]' || true
  fi
}

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-${PORT:-$(env_port_from_file)}}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
ORIGIN="${ORIGIN:-http://127.0.0.1:${FRONTEND_PORT}}"

PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

log() { printf '[run.sh] %s\n' "$*"; }
die() { printf '[run.sh] ERROR: %s\n' "$*" >&2; exit 1; }

need_cmd() { command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"; }

if [[ "$RUN_BACKEND" == 1 ]]; then
  need_cmd python3
  if [[ ! -x "$BACKEND_DIR/venv/bin/uvicorn" ]]; then
    if [[ "$DO_INSTALL" == 1 || ! -d "$BACKEND_DIR/venv" ]]; then
      log "creating backend venv + installing requirements…"
      python3 -m venv "$BACKEND_DIR/venv"
      "$BACKEND_DIR/venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
    else
      die "backend venv missing — re-run with --install"
    fi
  elif [[ "$DO_INSTALL" == 1 ]]; then
    log "installing backend requirements…"
    "$BACKEND_DIR/venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"
  fi
  [[ -f "$BACKEND_DIR/.env" ]] || log "warning: backend/.env missing — copy backend/.env.example"
fi

if [[ "$RUN_FRONTEND" == 1 ]]; then
  need_cmd node
  need_cmd npm
  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    if [[ "$DO_INSTALL" == 1 ]]; then
      log "installing frontend dependencies…"
      (cd "$FRONTEND_DIR" && npm install)
    else
      die "frontend/node_modules missing — run: cd frontend && npm install (or ./run.sh --install)"
    fi
  elif [[ "$DO_INSTALL" == 1 ]]; then
    log "installing frontend dependencies…"
    (cd "$FRONTEND_DIR" && npm install)
  fi
  if [[ "$DO_BUILD" == 1 ]]; then
    log "building frontend…"
    (cd "$FRONTEND_DIR" && npm run build)
  fi
  if [[ "$SKIP_BUILD_CHECK" == 0 && ! -f "$FRONTEND_DIR/build/index.js" ]]; then
    die "frontend/build missing — run: cd frontend && npm run build (or ./run.sh --build)"
  fi
  [[ -f "$FRONTEND_DIR/.env" ]] || log "warning: frontend/.env missing — PUBLIC_API_BASE unset for the browser"
fi

if [[ "$RUN_BACKEND" == 1 ]]; then
  log "starting backend: ${BACKEND_HOST}:${BACKEND_PORT} (app.main:app)"
  (cd "$BACKEND_DIR" && ./venv/bin/uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT") &
  PIDS+=($!)
fi

if [[ "$RUN_FRONTEND" == 1 ]]; then
  log "starting frontend: :${FRONTEND_PORT} (ORIGIN=${ORIGIN})"
  (cd "$FRONTEND_DIR" && PORT="$FRONTEND_PORT" ORIGIN="$ORIGIN" node build) &
  PIDS+=($!)
fi

# Wait until the backend answers /api/health (backend-only or full mode).
if [[ "$RUN_BACKEND" == 1 ]]; then
  log "waiting for backend /api/health…"
  for _ in $(seq 1 60); do
    if python3 -c "
import sys, urllib.request
try:
    r = urllib.request.urlopen('http://${BACKEND_HOST}:${BACKEND_PORT}/api/health', timeout=2)
    sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
      log "backend up: http://${BACKEND_HOST}:${BACKEND_PORT}/api/health"
      break
    fi
    sleep 1
    if [[ "$_" == 60 ]]; then
      die "backend did not become healthy in 60s"
    fi
  done
fi

if [[ "$RUN_FRONTEND" == 1 && "$RUN_BACKEND" == 1 ]]; then
  log "app running — frontend http://127.0.0.1:${FRONTEND_PORT} → backend http://${BACKEND_HOST}:${BACKEND_PORT}"
elif [[ "$RUN_FRONTEND" == 1 ]]; then
  log "frontend running — http://127.0.0.1:${FRONTEND_PORT} (start a backend separately)"
else
  log "backend running — http://${BACKEND_HOST}:${BACKEND_PORT}"
fi
log "Ctrl-C to stop."

wait
