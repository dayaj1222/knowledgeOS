#!/usr/bin/env bash
# Run the local production build: Vite assets served by FastAPI on :8000.
# Ctrl+C stops the app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_PID=""

cleanup() {
  echo
  echo "Shutting down..."
  if [[ -n "$BACKEND_PID" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  # kill the whole process group (uvicorn may spawn children)
  [[ -n "$BACKEND_PID" ]] && pkill -P "$BACKEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

# Free the ports first so stale processes don't block startup.
close_port() {
  local port="$1"
  local pids

  # Match any address bound to this port (0.0.0.0, 127.0.0.1, ::, etc.)
  pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"

  # Fallback for systems where lsof isn't available or misses the listener.
  if [[ -z "$pids" ]] && command -v fuser >/dev/null 2>&1; then
    pids="$(fuser "$port"/tcp 2>/dev/null || true)"
  fi

  if [[ -n "$pids" ]]; then
    echo "Port $port is in use; killing: $pids"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 0.5

    # Re-check and escalate to SIGKILL for anything that ignored SIGTERM.
    pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -z "$pids" ]] && command -v fuser >/dev/null 2>&1; then
      pids="$(fuser "$port"/tcp 2>/dev/null || true)"
    fi
    if [[ -n "$pids" ]]; then
      echo "Port $port still in use; force-killing: $pids"
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
      sleep 0.5
    fi
  fi
}

close_port 8000
# Build once, then serve the production assets from FastAPI. Vite's dev
# server and hot reload are intentionally not part of this launcher.
echo "Building frontend production assets ..."
cd "$ROOT/frontend"
npm run build

echo "Starting app on http://localhost:8000 ..."
cd "$ROOT"
uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo
echo "  app:    http://localhost:8000"
echo "  health: http://localhost:8000/health"
echo
echo "Press Ctrl+C to stop both."
wait
