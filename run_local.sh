#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.11/3.12/3.13 and retry."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js/npm and retry."
  exit 1
fi

if [[ ! -d "${BACKEND_DIR}" || ! -d "${FRONTEND_DIR}" ]]; then
  echo "Expected backend/ and frontend/ folders under: ${ROOT_DIR}"
  exit 1
fi

echo "Project root: ${ROOT_DIR}"
echo "Backend URL:  http://localhost:${BACKEND_PORT}"
echo "Frontend URL: http://localhost:${FRONTEND_PORT}"
echo

# --- Backend setup ---
cd "${BACKEND_DIR}"

if [[ ! -d ".venv" ]]; then
  echo "[backend] Creating virtualenv..."
  python3 -m venv .venv
fi

VENV_PY="${BACKEND_DIR}/.venv/bin/python3"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "[backend] Virtualenv python not found at ${VENV_PY}"
  echo "[backend] Recreating virtualenv..."
  rm -rf .venv
  python3 -m venv .venv
  VENV_PY="${BACKEND_DIR}/.venv/bin/python3"
fi

if ! "${VENV_PY}" -c "import sys" >/dev/null 2>&1; then
  echo "[backend] Virtualenv looks stale after path rename. Recreating..."
  rm -rf .venv
  python3 -m venv .venv
  VENV_PY="${BACKEND_DIR}/.venv/bin/python3"
fi

if [[ "${SKIP_INSTALL}" != "1" ]]; then
  echo "[backend] Installing Python dependencies..."
  # Use python -m pip so we avoid stale pip shebangs after folder moves/renames.
  "${VENV_PY}" -m pip install -r requirements.txt
else
  echo "[backend] SKIP_INSTALL=1, skipping pip install."
fi

echo "[backend] Starting API server..."
"${VENV_PY}" -m uvicorn app.main:app --reload --port "${BACKEND_PORT}" &
BACKEND_PID=$!

# --- Frontend setup ---
cd "${FRONTEND_DIR}"

if [[ "${SKIP_INSTALL}" != "1" ]]; then
  echo "[frontend] Installing npm dependencies..."
  npm install
else
  echo "[frontend] SKIP_INSTALL=1, skipping npm install."
fi

echo "[frontend] Starting dashboard..."
npm run dev -- --port "${FRONTEND_PORT}" &
FRONTEND_PID=$!

cleanup() {
  echo
  echo "Stopping services..."
  kill "${BACKEND_PID}" "${FRONTEND_PID}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo
echo "Stock Tiger is starting..."
echo "Press Ctrl+C to stop both services."
echo

# macOS default Bash (3.2) does not support `wait -n`.
# Poll PIDs and exit when either process stops.
while true; do
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    wait "${BACKEND_PID}" 2>/dev/null || true
    break
  fi
  if ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    wait "${FRONTEND_PID}" 2>/dev/null || true
    break
  fi
  sleep 1
done
