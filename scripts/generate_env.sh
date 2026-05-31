#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

rand_hex() {
  openssl rand -hex 32
}

add_if_missing() {
  local key="$1"
  local value="$2"

  touch .env

  if ! grep -q "^${key}=" .env; then
    echo "${key}=${value}" >> .env
    echo "ADD ${key}"
  else
    echo "OK  ${key}"
  fi
}

echo "Asegurando .env con claves seguras..."

add_if_missing POSTGRES_USER "admin_angio"
add_if_missing POSTGRES_PASSWORD "$(rand_hex)"
add_if_missing POSTGRES_DB "angiopacs_db"

add_if_missing PORT_BACKEND "8000"
add_if_missing ANGIOPACS_USER "admin"
add_if_missing ANGIOPACS_PASSWORD "$(rand_hex)"
add_if_missing ANGIOPACS_SESSION_SECRET "$(openssl rand -hex 48)"
add_if_missing ANGIOPACS_BOOTSTRAP_ADMIN "true"

add_if_missing TELEGRAM_TOKEN "CAMBIAR_TOKEN_TELEGRAM"

add_if_missing PORT_ORTHANC_WEB "8042"
add_if_missing PORT_ORTHANC_DICOM "4242"
add_if_missing ORTHANC_NAME "NeuroPACS"
add_if_missing ORTHANC_AETITLE "ORTHANC"
add_if_missing ORTHANC_URL "http://orthanc-pacs:8042"
add_if_missing ORTHANC_PUBLIC_URL "http://localhost:8042"
add_if_missing ORTHANC_AUTHENTICATION_ENABLED "false"

add_if_missing ORTHANC_BACKEND_USER "angio_backend"
add_if_missing ORTHANC_BACKEND_PASSWORD "$(rand_hex)"

add_if_missing ORTHANC_ADMIN_USER "egidio_orthanc"
add_if_missing ORTHANC_ADMIN_PASSWORD "$(rand_hex)"

add_if_missing ORTHANC_VISIT_USER "visita"
add_if_missing ORTHANC_VISIT_PASSWORD "$(rand_hex)"

echo
echo "Listo."
echo "Archivo .env actualizado sin sobrescribir claves existentes."
echo "Para regenerar todo desde cero: elimina .env y vuelve a ejecutar este script."
