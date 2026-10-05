#!/usr/bin/env bash
# Start the website on macOS / Linux: the API on port 8002 and the web page on port 5173, then open the browser.
# Press Ctrl+C in this terminal to stop both. (Windows: double-click scripts/start_website.bat instead.)
# Runs from the repository root (this script lives in scripts/).
set -euo pipefail

cd "$(dirname "$0")/.."

API_PORT=8002
WEB_PORT=5173

if [ ! -x ".venv/bin/python" ]; then
  echo "Creating the website's Python environment once..."
  python3 -m venv .venv
  .venv/bin/python -m pip install -r backend/app/requirements.txt
fi
if [ ! -d "frontend/node_modules" ]; then
  echo "Installing the website packages once..."
  (cd frontend && npm install)
fi
if [ ! -f "frontend/.env" ]; then
  echo "VITE_API_URL=http://127.0.0.1:${API_PORT}" > frontend/.env
fi
# The v3 Demo / Pipeline pages run sem_pipeline with a Python that has PyTorch (see README).
if [ ! -f "sem_pipeline/website/v3_python.txt" ]; then
  found=""
  for candidate in python3 python; do
    if command -v "$candidate" > /dev/null 2>&1 &&
      "$candidate" -c "import sys, torch; open('sem_pipeline/website/v3_python.txt', 'w').write(sys.executable)" \
        > /dev/null 2>&1; then
      found=1
      break
    fi
  done
  if [ -z "$found" ]; then
    echo "WARNING: no Python with PyTorch found - the Demo and Pipeline pages will not run new images."
    echo "         Install it, see README \"Quick start\"."
  fi
fi

# Each server runs in its own process group (set -m), so Ctrl+C here stops the servers and their children.
set -m
pids=()
stop() {
  trap - INT TERM EXIT
  echo
  echo "Stopping the website..."
  for pid in ${pids[@]+"${pids[@]}"}; do
    kill -TERM -- "-$pid" 2> /dev/null || kill -TERM "$pid" 2> /dev/null || true
  done
  wait 2> /dev/null || true
}
trap 'stop; exit 130' INT
trap 'stop; exit 143' TERM
trap stop EXIT

.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --port "$API_PORT" &
pids+=($!)
(cd frontend && exec npm run dev) &
pids+=($!)

echo "Starting... the browser opens in a few seconds. Press Ctrl+C to stop."
sleep 7
url="http://localhost:${WEB_PORT}"
if command -v open > /dev/null 2>&1 && [ "$(uname -s)" = "Darwin" ]; then
  open "$url"
elif command -v xdg-open > /dev/null 2>&1; then
  xdg-open "$url" > /dev/null 2>&1 || true
else
  echo "Open $url in your browser."
fi

# Stay in the foreground until a server exits or Ctrl+C is pressed.
wait -n 2> /dev/null || wait
