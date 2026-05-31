#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "===== NeuroPACS / AngioPACS up ====="
echo "Ruta: $ROOT_DIR"
echo

if [ ! -f ".env" ]; then
  echo "No existe .env."
  echo "Ejecutando wizard: scripts/generate_env.sh"
  echo
  scripts/generate_env.sh
else
  echo "OK: .env existe. No se regenera."
fi

echo
echo "===== Generar config Orthanc ====="
if [ -x "scripts/generate_orthanc_config.sh" ]; then
  scripts/generate_orthanc_config.sh
else
  chmod +x scripts/generate_orthanc_config.sh
  scripts/generate_orthanc_config.sh
fi

echo
echo "===== Levantar Docker Compose ====="
docker compose up -d --build

echo
echo "===== Estado ====="
docker compose ps

echo
echo "===== Validacion basica ====="
if [ -x "scripts/check_neuropacs.sh" ]; then
  scripts/check_neuropacs.sh
else
  chmod +x scripts/check_neuropacs.sh
  scripts/check_neuropacs.sh
fi
