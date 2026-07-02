#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"
GIT_CODES_DIR="$(cd "${ROOT_DIR}/.." && pwd)"
PYENV_GLOBAL="${PYENV_GLOBAL:-${GIT_CODES_DIR}/pyenv_global}"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
RUNTIME_MODE="${RUNTIME_MODE:-production}"
SKIP_INSTALL="${SKIP_INSTALL:-0}"
BACKEND_DETACH="${BACKEND_DETACH:-1}"
LOGS_DIR="${LOGS_DIR:-${ROOT_DIR}/logs}"
BACKEND_LOG="${BACKEND_LOG:-${LOGS_DIR}/backend.log}"
FRONTEND_LOG="${FRONTEND_LOG:-${LOGS_DIR}/frontend.log}"
BACKEND_PID_FILE="${BACKEND_PID_FILE:-${LOGS_DIR}/backend.pid}"
APP_NDJSON_LOG="${APP_NDJSON_LOG:-${LOGS_DIR}/app.ndjson}"

mkdir -p "${LOGS_DIR}"

require_free_port() {
  local label="$1"
  local port="$2"

  if lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "${label} port ${port} is already in use."
    echo
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN || true
    echo
    echo "Stop the existing process or use a different port, for example:"
    if [[ "${label}" == "Backend" ]]; then
      echo "  BACKEND_PORT=8010 ./run_local.sh"
    else
      echo "  FRONTEND_PORT=3010 ./run_local.sh"
    fi
    exit 1
  fi
}

kill_existing_port_process() {
  local label="$1"
  local port="$2"
  local pids

  pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    return
  fi

  echo "${label} port ${port} is already in use. Stopping existing process(es): ${pids}"
  kill ${pids} 2>/dev/null || true

  for _ in {1..20}; do
    if ! lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "${label} port ${port} is free."
      return
    fi
    sleep 0.25
  done

  echo "${label} port ${port} is still busy. Force-stopping process(es): ${pids}"
  kill -9 ${pids} 2>/dev/null || true
  sleep 0.25
}

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not found. Install Node.js/npm and retry."
  exit 1
fi

if [[ ! -d "${BACKEND_DIR}" || ! -d "${FRONTEND_DIR}" ]]; then
  echo "Expected backend/ and frontend/ folders under: ${ROOT_DIR}"
  exit 1
fi

if [[ ! -x "${PYENV_GLOBAL}/bin/python" ]]; then
  echo "Shared venv not found: ${PYENV_GLOBAL}"
  echo "Run: python3.12 -m venv ${PYENV_GLOBAL} && source ${PYENV_GLOBAL}/bin/activate && pip install poetry"
  echo "Then: cd ${BACKEND_DIR} && poetry install"
  exit 1
fi

echo "Project root: ${ROOT_DIR}"
echo "Python env:   ${PYENV_GLOBAL}"
echo "Backend URL:  http://localhost:${BACKEND_PORT}"
echo "Frontend URL: http://localhost:${FRONTEND_PORT}"
echo "Runtime mode: ${RUNTIME_MODE} (production=live IBKR, testing=fixture)"
echo "App logs:     ${LOGS_DIR}/"
echo "  backend:    ${BACKEND_LOG}"
echo "  frontend:   ${FRONTEND_LOG}"
echo "  structured: ${APP_NDJSON_LOG}"
echo

kill_existing_port_process "Backend" "${BACKEND_PORT}"
require_free_port "Backend" "${BACKEND_PORT}"
require_free_port "Frontend" "${FRONTEND_PORT}"

# --- Backend setup ---
cd "${BACKEND_DIR}"
export VIRTUAL_ENV="${PYENV_GLOBAL}"
export PATH="${PYENV_GLOBAL}/bin:${PATH}"

if [[ -f "pyproject.toml" && -x "${PYENV_GLOBAL}/bin/poetry" ]]; then
  if [[ "${SKIP_INSTALL}" != "1" ]]; then
    echo "[backend] Installing dependencies with Poetry (pyenv_global)..."
    poetry install
  else
    echo "[backend] SKIP_INSTALL=1, skipping poetry install."
  fi
  if [[ "${BACKEND_DETACH}" == "1" ]]; then
    echo "[backend] Starting API server detached..."
    nohup poetry run uvicorn app.main:app --reload --port "${BACKEND_PORT}" > "${BACKEND_LOG}" 2>&1 &
    BACKEND_PID=$!
    echo "${BACKEND_PID}" > "${BACKEND_PID_FILE}"
    echo "[backend] PID ${BACKEND_PID}; log: ${BACKEND_LOG}"
  else
    echo "[backend] Starting API server..."
    poetry run uvicorn app.main:app --reload --port "${BACKEND_PORT}" &
    BACKEND_PID=$!
  fi
else
  echo "[backend] Poetry/pyproject.toml not available; using pip + requirements.txt"
  if [[ "${SKIP_INSTALL}" != "1" ]]; then
    "${PYENV_GLOBAL}/bin/pip" install -r requirements.txt
  fi
  if [[ "${BACKEND_DETACH}" == "1" ]]; then
    echo "[backend] Starting API server detached..."
    nohup "${PYENV_GLOBAL}/bin/python" -m uvicorn app.main:app --reload --port "${BACKEND_PORT}" > "${BACKEND_LOG}" 2>&1 &
    BACKEND_PID=$!
    echo "${BACKEND_PID}" > "${BACKEND_PID_FILE}"
    echo "[backend] PID ${BACKEND_PID}; log: ${BACKEND_LOG}"
  else
    "${PYENV_GLOBAL}/bin/python" -m uvicorn app.main:app --reload --port "${BACKEND_PORT}" &
    BACKEND_PID=$!
  fi
fi

sleep 1
if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
  echo "[backend] Failed to start. Check log: ${BACKEND_LOG}"
  exit 1
fi

# --- Frontend setup ---
cd "${FRONTEND_DIR}"

if [[ "${SKIP_INSTALL}" != "1" ]]; then
  echo "[frontend] Installing npm dependencies..."
  npm install
else
  echo "[frontend] SKIP_INSTALL=1, skipping npm install."
fi

echo "[frontend] Starting dashboard (log: ${FRONTEND_LOG})..."
npm run dev -- --port "${FRONTEND_PORT}" 2>&1 | tee "${FRONTEND_LOG}" &
FRONTEND_PID=$!

cleanup() {
  echo
  echo "Stopping frontend..."
  kill "${FRONTEND_PID}" 2>/dev/null || true
  if [[ "${BACKEND_DETACH}" == "1" ]]; then
    echo "Backend is still running on port ${BACKEND_PORT} (PID ${BACKEND_PID})."
    echo "Stop it with: kill ${BACKEND_PID}"
  else
    echo "Stopping backend..."
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

echo
echo "Billion Dollar is starting..."
if [[ "${BACKEND_DETACH}" == "1" ]]; then
  echo "Backend is detached and will keep running if this terminal closes."
  echo "Press Ctrl+C to stop the frontend only."
else
  echo "Press Ctrl+C to stop both services."
fi
echo

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
