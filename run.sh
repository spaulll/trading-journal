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
#   BACKEND_HOST      default 0.0.0.0 (loopback-only breaks laptop/LAN browsers:
#                     the browser fetches the API directly, so the backend must
#                     listen on a browser-reachable interface)
#   BACKEND_PORT      default: $PORT from backend/.env, else 8000
#   FRONTEND_PORT     default 3000
#   ORIGIN            default http://127.0.0.1:<FRONTEND_PORT> (set to the URL
#                     you open in the browser when on LAN, e.g.
#                     ORIGIN=http://10.10.10.162:3000)
#   PUBLIC_API_BASE   backend URL the *browser* calls (explicit env wins, then
#                     frontend/.env, then http://127.0.0.1:<BACKEND_PORT>).
#                     Exported so the SvelteKit server uses it at runtime.
#                     Browsing via a LAN IP also needs that page origin in
#                     backend/.env CORS_ORIGINS.
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

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-${PORT:-$(env_port_from_file)}}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
ORIGIN="${ORIGIN:-http://127.0.0.1:${FRONTEND_PORT}}"

# Health checks always hit loopback even when bound to 0.0.0.0.
HEALTH_HOST="$BACKEND_HOST"
if [[ "$HEALTH_HOST" == "0.0.0.0" || "$HEALTH_HOST" == "::" ]]; then
  HEALTH_HOST="127.0.0.1"
fi

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

url_host() {
  # Extract host from a URL (drops scheme, port, path).
  local u="${1#*://}"
  u="${u%%/*}"
  printf '%s' "${u%%:*}"
}

is_loopback() {
  case "$1" in
    127.*|localhost|::1) return 0 ;;
    *) return 1 ;;
  esac
}

resolve_api_base() {
  # API URL the browser calls: explicit env wins, then frontend/.env,
  # then a loopback fallback. Exported so the SvelteKit server
  # ($env/dynamic/public) uses it at runtime.
  if [[ -z "${PUBLIC_API_BASE:-}" && -f "$FRONTEND_DIR/.env" ]]; then
    PUBLIC_API_BASE="$(grep -E '^[[:space:]]*PUBLIC_API_BASE=' "$FRONTEND_DIR/.env" | tail -n1 | cut -d= -f2- | tr -d '[:space:]' || true)"
  fi
  PUBLIC_API_BASE="${PUBLIC_API_BASE:-http://127.0.0.1:${BACKEND_PORT}}"
  export PUBLIC_API_BASE
}

preflight() {
  # Warn about the two classic "Backend unreachable" causes: backend bound
  # to loopback while the browser uses a LAN URL, and a LAN page origin
  # missing from backend CORS_ORIGINS.
  local api_host origin_host cors
  api_host="$(url_host "$PUBLIC_API_BASE")"
  origin_host="$(url_host "$ORIGIN")"
  if ! is_loopback "$api_host" && is_loopback "$BACKEND_HOST"; then
    log "WARNING: browsers call the API at ${PUBLIC_API_BASE}, but the backend binds ${BACKEND_HOST} (loopback-only)."
    log "WARNING: start with BACKEND_HOST=0.0.0.0 so the API is reachable on the LAN."
  fi
  if ! is_loopback "$origin_host"; then
    cors="$(grep -E '^[[:space:]]*CORS_ORIGINS=' "$BACKEND_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '[:space:]' || true)"
    if [[ "$cors" != *"$ORIGIN"* ]]; then
      log "WARNING: opening the frontend at ${ORIGIN} needs that origin in backend/.env CORS_ORIGINS"
      log "WARNING: (backend only allows localhost/127.0.0.1 :3000/:5173 by default)."
    fi
  fi
  log "browser → API: ${PUBLIC_API_BASE} (backend ${BACKEND_HOST}:${BACKEND_PORT})"
}

resolve_api_base
preflight

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
    r = urllib.request.urlopen('http://${HEALTH_HOST}:${BACKEND_PORT}/api/health', timeout=2)
    sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
      log "backend up: http://${HEALTH_HOST}:${BACKEND_PORT}/api/health"
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
