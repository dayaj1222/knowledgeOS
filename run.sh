#!/usr/bin/env bash
# Run the knowledge-base app: FastAPI backend (:8000) + Vite frontend (:5173).
# Ctrl+C stops both.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo
  echo "Shutting down..."
  if [[ -n "$BACKEND_PID" ]]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
  if [[ -n "$FRONTEND_PID" ]]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
  # kill the whole process groups (uvicorn/vite spawn children)
  [[ -n "$BACKEND_PID" ]] && pkill -P "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && pkill -P "$FRONTEND_PID" 2>/dev/null || true
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
close_port 5173

echo "Starting backend on http://localhost:8000 ..."
cd "$ROOT"
uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting frontend on http://localhost:5173 ..."
cd "$ROOT/frontend"
npm run dev &
FRONTEND_PID=$!

echo
echo "  backend:  http://localhost:8000  (health: /health)"
echo "  frontend: http://localhost:5173"
echo
echo "Press Ctrl+C to stop both."
wait
