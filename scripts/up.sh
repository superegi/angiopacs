#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f ".env" ]]; then
  echo "No existe .env. Generando desde .env.example..."
  scripts/generate_env.sh "$@"
else
  echo "OK: .env existe. No se modifica."
fi

docker compose up -d --build
