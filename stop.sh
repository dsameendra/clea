#!/usr/bin/env bash
# Stop the Clea server started with ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

PID_FILE=data/clea.pid
if [ ! -f "$PID_FILE" ]; then
  echo "Clea is not running."
  exit 0
fi
PID=$(cat "$PID_FILE")
if ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PID_FILE" data/clea.port
  echo "Clea is not running."
  exit 0
fi
if ! ps -p "$PID" -o command= | grep -q "clea serve"; then
  rm -f "$PID_FILE" data/clea.port
  echo "Process $PID is not Clea; left it alone."
  exit 1
fi

kill "$PID"
# A running crawl stops at its next request; allow for one in-flight request (15 s timeout).
for _ in $(seq 1 60); do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE" data/clea.port
    echo "Clea stopped. (Pages already crawled are saved; the next crawl picks up the rest.)"
    exit 0
  fi
  sleep 0.5
done
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE" data/clea.port
echo "Clea stopped (forced after 30 s)."
