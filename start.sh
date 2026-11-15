#!/usr/bin/env bash
# Start Clea in the background → http://localhost:6942   (stop it with ./stop.sh)
#
# First run sets everything up: a Python virtualenv in .venv, the Python packages, and
# the web interface build. Later runs only redo those steps when something changed.
# Settings come from CLEA_* environment variables (see README), e.g. CLEA_PORT=8080 ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

PID_FILE=data/clea.pid
LOG_FILE=data/clea.log
PORT="${CLEA_PORT:-6942}"
mkdir -p data

if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "Clea is already running at http://localhost:$PORT (pid $(cat "$PID_FILE"))."
  exit 0
fi

# Python environment
if [ ! -x .venv/bin/python ]; then
  PYTHON=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3 || true)
  if [ -z "$PYTHON" ]; then echo "Python 3.11+ is required: https://www.python.org/downloads/"; exit 1; fi
  echo "Creating Python environment (first run)…"
  "$PYTHON" -m venv .venv
fi
if [ ! -f .venv/.clea-requirements ] || [ requirements.txt -nt .venv/.clea-requirements ]; then
  echo "Installing Python packages…"
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -r requirements.txt
  touch .venv/.clea-requirements
fi

# Web interface (rebuilt when its sources are newer than the last build)
if [ ! -f frontend/dist/index.html ] || \
   [ -n "$(find frontend/src frontend/public frontend/index.html frontend/package.json frontend/vite.config.js -newer frontend/dist/index.html -print -quit)" ]; then
  if ! command -v npm >/dev/null; then echo "Node.js 20+ is required to build the web interface: https://nodejs.org/"; exit 1; fi
  echo "Building the web interface…"
  if [ ! -f frontend/node_modules/.package-lock.json ] || [ frontend/package-lock.json -nt frontend/node_modules/.package-lock.json ]; then
    (cd frontend && npm ci --no-audit --no-fund --loglevel=error)
  fi
  (cd frontend && npm run build --silent >/dev/null)
fi

echo "Starting Clea…"
nohup .venv/bin/python -m clea serve >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    echo "Clea is running at http://localhost:$PORT  (pid $(cat "$PID_FILE"), log: $LOG_FILE)"
    exit 0
  fi
  if ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Clea failed to start. Last lines of $LOG_FILE:"
    tail -n 15 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
  fi
  sleep 0.5
done
echo "Clea is still starting (pid $(cat "$PID_FILE")); see $LOG_FILE"
