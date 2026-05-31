#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

BASE_URL="${1:-${WEB_PUBLIC_URL:-http://127.0.0.1:${PORT_BACKEND:-8000}}}"
ORTHANC_WEB_PORT="${PORT_ORTHANC_WEB:-8042}"

echo "===== CHECK NEUROPACS ====="
echo "BASE_URL=${BASE_URL}"
echo "ORTHANC_WEB_PORT=${ORTHANC_WEB_PORT}"
echo

echo "===== Web / gateway ====="
curl -sS -o /dev/null -w "/ -> %{http_code}\n" "${BASE_URL}/" || true
curl -sS -o /dev/null -w "/login -> %{http_code}\n" "${BASE_URL}/login" || true
curl -sS -o /dev/null -w "/orthanc/system -> %{http_code}\n" "${BASE_URL}/orthanc/system" || true

echo
echo "===== Orthanc directo local ====="
curl -sS -o /dev/null -w "orthanc directo /system -> %{http_code}\n" "http://127.0.0.1:${ORTHANC_WEB_PORT}/system" || true

echo
echo "===== Resultado esperado sin sesion ====="
echo "/ -> 303"
echo "/login -> 200"
echo "/orthanc/system -> 303"
echo "orthanc directo /system -> 401"
echo
echo "===== FIN CHECK ====="
