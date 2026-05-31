#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_EXAMPLE=".env.example"
ENV_FILE=".env"
CREDENTIALS_FILE=".env.credentials.txt"

usage() {
  cat <<EOF
Uso:
  scripts/generate_env.sh [opciones]

Opciones:
  --force                     Regenera .env aunque ya exista. Crea backup previo.
  --profile servlocal         Perfil para despliegue con Traefik externo por NetBird/VPN.
  --web-url URL               URL pública de la web AngioPACS.
  --orthanc-public-url URL    URL pública de Orthanc.
  --backend-port PUERTO       Puerto host para la web.
  --orthanc-web-port PUERTO   Puerto host para Orthanc Web.
  --orthanc-dicom-port PUERTO Puerto host para Orthanc DICOM.
  --orthanc-bind ADDRESS      Dirección bind host: 127.0.0.1 o 0.0.0.0.
  --telegram-token TOKEN      Token Telegram.
  -h, --help                  Muestra esta ayuda.

Comportamiento:
  - Si .env existe y no usas --force, no lo modifica.
  - Si .env no existe, lo crea desde .env.example.
  - Genera claves seguras hexadecimales, sin caracteres problemáticos para docker compose.
EOF
}

FORCE=0
PROFILE=""

WEB_PUBLIC_URL=""
ANGIOPACS_PUBLIC_URL=""
ORTHANC_PUBLIC_URL=""
PORT_BACKEND=""
PORT_ORTHANC_WEB=""
PORT_ORTHANC_DICOM=""
ORTHANC_BIND_ADDRESS=""
TELEGRAM_TOKEN_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    --profile)
      PROFILE="${2:-}"
      shift 2
      ;;
    --web-url)
      WEB_PUBLIC_URL="${2:-}"
      ANGIOPACS_PUBLIC_URL="${2:-}"
      shift 2
      ;;
    --orthanc-public-url)
      ORTHANC_PUBLIC_URL="${2:-}"
      shift 2
      ;;
    --backend-port)
      PORT_BACKEND="${2:-}"
      shift 2
      ;;
    --orthanc-web-port)
      PORT_ORTHANC_WEB="${2:-}"
      shift 2
      ;;
    --orthanc-dicom-port)
      PORT_ORTHANC_DICOM="${2:-}"
      shift 2
      ;;
    --orthanc-bind)
      ORTHANC_BIND_ADDRESS="${2:-}"
      shift 2
      ;;
    --telegram-token)
      TELEGRAM_TOKEN_ARG="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: opción no reconocida: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ ! -f "$ENV_EXAMPLE" ]]; then
  echo "ERROR: no existe $ENV_EXAMPLE" >&2
  exit 1
fi

if [[ -f "$ENV_FILE" && "$FORCE" -ne 1 ]]; then
  echo "OK: $ENV_FILE ya existe. No se modifica."
  echo "Para regenerar: scripts/generate_env.sh --force"
  exit 0
fi

if [[ -f "$ENV_FILE" && "$FORCE" -eq 1 ]]; then
  BACKUP=".env.backup_$(date +%F_%H%M%S)"
  cp "$ENV_FILE" "$BACKUP"
  chmod 600 "$BACKUP"
  echo "Backup creado: $BACKUP"
fi

umask 077
cp "$ENV_EXAMPLE" "$ENV_FILE"
chmod 600 "$ENV_FILE"

rand_hex() {
  openssl rand -hex "${1:-24}"
}

set_kv() {
  local key="$1"
  local val="$2"

  if grep -qE "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
}

get_kv() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2-
}

POSTGRES_USER="$(get_kv POSTGRES_USER)"
POSTGRES_DB="$(get_kv POSTGRES_DB)"
ANGIOPACS_USER="$(get_kv ANGIOPACS_USER)"
ORTHANC_BACKEND_USER="$(get_kv ORTHANC_BACKEND_USER)"
ORTHANC_ADMIN_USER="$(get_kv ORTHANC_ADMIN_USER)"
ORTHANC_VISIT_USER="$(get_kv ORTHANC_VISIT_USER)"

POSTGRES_USER="${POSTGRES_USER:-admin_angio}"
POSTGRES_DB="${POSTGRES_DB:-angiopacs_db}"
ANGIOPACS_USER="${ANGIOPACS_USER:-admin}"
ORTHANC_BACKEND_USER="${ORTHANC_BACKEND_USER:-angio_backend}"
ORTHANC_ADMIN_USER="${ORTHANC_ADMIN_USER:-egidio_orthanc}"
ORTHANC_VISIT_USER="${ORTHANC_VISIT_USER:-visita}"

POSTGRES_PASSWORD="$(rand_hex 24)"
ANGIOPACS_PASSWORD="$(rand_hex 16)"
ANGIOPACS_SESSION_SECRET="$(rand_hex 32)"
ORTHANC_BACKEND_PASSWORD="$(rand_hex 24)"
ORTHANC_ADMIN_PASSWORD="$(rand_hex 24)"
ORTHANC_VISIT_PASSWORD="$(rand_hex 24)"

: "${WEB_PUBLIC_URL:=http://localhost:8000}"
: "${ANGIOPACS_PUBLIC_URL:=$WEB_PUBLIC_URL}"
: "${ORTHANC_PUBLIC_URL:=http://localhost:8042}"
: "${PORT_BACKEND:=8000}"
: "${PORT_ORTHANC_WEB:=8042}"
: "${PORT_ORTHANC_DICOM:=4242}"
: "${ORTHANC_BIND_ADDRESS:=127.0.0.1}"

if [[ "$PROFILE" == "servlocal" ]]; then
  [[ "$WEB_PUBLIC_URL" == "http://localhost:8000" ]] && WEB_PUBLIC_URL="https://neurobib.rix.cl"
  [[ "$ANGIOPACS_PUBLIC_URL" == "http://localhost:8000" ]] && ANGIOPACS_PUBLIC_URL="https://neurobib.rix.cl"
  [[ "$ORTHANC_PUBLIC_URL" == "http://localhost:8042" ]] && ORTHANC_PUBLIC_URL="https://neuropacs.rix.cl"
  [[ "$PORT_BACKEND" == "8000" ]] && PORT_BACKEND="8001"
  [[ "$ORTHANC_BIND_ADDRESS" == "127.0.0.1" ]] && ORTHANC_BIND_ADDRESS="0.0.0.0"
fi

set_kv TZ "America/Santiago"

set_kv POSTGRES_USER "$POSTGRES_USER"
set_kv POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
set_kv POSTGRES_DB "$POSTGRES_DB"

set_kv PORT_BACKEND "$PORT_BACKEND"

set_kv ANGIOPACS_USER "$ANGIOPACS_USER"
set_kv ANGIOPACS_PASSWORD "$ANGIOPACS_PASSWORD"
set_kv ANGIOPACS_SESSION_SECRET "$ANGIOPACS_SESSION_SECRET"
set_kv ANGIOPACS_BOOTSTRAP_ADMIN "true"

set_kv TELEGRAM_TOKEN "$TELEGRAM_TOKEN_ARG"

set_kv PORT_ORTHANC_WEB "$PORT_ORTHANC_WEB"
set_kv PORT_ORTHANC_DICOM "$PORT_ORTHANC_DICOM"
set_kv ORTHANC_BIND_ADDRESS "$ORTHANC_BIND_ADDRESS"

set_kv ORTHANC_NAME "NeuroPACS"
set_kv ORTHANC_AETITLE "$(get_kv ORTHANC_AETITLE)"
set_kv ORTHANC_URL "http://orthanc-pacs:8042"
set_kv ORTHANC_PUBLIC_URL "$ORTHANC_PUBLIC_URL"
set_kv ORTHANC_AUTHENTICATION_ENABLED "true"

set_kv ORTHANC_BACKEND_USER "$ORTHANC_BACKEND_USER"
set_kv ORTHANC_BACKEND_PASSWORD "$ORTHANC_BACKEND_PASSWORD"

set_kv ORTHANC_ADMIN_USER "$ORTHANC_ADMIN_USER"
set_kv ORTHANC_ADMIN_PASSWORD "$ORTHANC_ADMIN_PASSWORD"

set_kv ORTHANC_VISIT_USER "$ORTHANC_VISIT_USER"
set_kv ORTHANC_VISIT_PASSWORD "$ORTHANC_VISIT_PASSWORD"

# Compatibilidad con código actual.
set_kv ORTHANC_USER "$ORTHANC_BACKEND_USER"
set_kv ORTHANC_PASSWORD "$ORTHANC_BACKEND_PASSWORD"

set_kv WEB_PUBLIC_URL "$WEB_PUBLIC_URL"
set_kv ANGIOPACS_PUBLIC_URL "$ANGIOPACS_PUBLIC_URL"
set_kv DATABASE_URL "postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres-db:5432/${POSTGRES_DB}"

cat > "$CREDENTIALS_FILE" <<EOF
Credenciales generadas para AngioPACS / NeuroPACS

WEB:
URL: ${WEB_PUBLIC_URL}
Usuario: ${ANGIOPACS_USER}
Clave: ${ANGIOPACS_PASSWORD}

ORTHANC ADMIN:
URL: ${ORTHANC_PUBLIC_URL}
Usuario: ${ORTHANC_ADMIN_USER}
Clave: ${ORTHANC_ADMIN_PASSWORD}

ORTHANC BACKEND:
Usuario: ${ORTHANC_BACKEND_USER}
Clave: ${ORTHANC_BACKEND_PASSWORD}

ORTHANC VISITA:
Usuario: ${ORTHANC_VISIT_USER}
Clave: ${ORTHANC_VISIT_PASSWORD}
EOF

chmod 600 "$CREDENTIALS_FILE"

BAD_PLACEHOLDERS="$(grep -nE '^[A-Z0-9_]+=.*(GENERAR|CAMBIAR|1234qwer|super_secreto|super_secret|CAMBIAR_POSTGRES_PASSWORD)' "$ENV_FILE" || true)"

if [[ -n "$BAD_PLACEHOLDERS" ]]; then
  echo "ERROR: quedaron placeholders inseguros en $ENV_FILE:" >&2
  echo "$BAD_PLACEHOLDERS" >&2
  exit 1
fi

if grep -q '\$' "$ENV_FILE"; then
  echo "ERROR: hay signos \$ en $ENV_FILE. Docker Compose podría interpretarlos mal." >&2
  grep -n '\$' "$ENV_FILE" >&2
  exit 1
fi

echo "OK: $ENV_FILE generado."
echo "OK: credenciales guardadas en $CREDENTIALS_FILE"
echo
grep -E '^(PORT_BACKEND|PORT_ORTHANC_WEB|PORT_ORTHANC_DICOM|ORTHANC_BIND_ADDRESS|WEB_PUBLIC_URL|ANGIOPACS_PUBLIC_URL|ORTHANC_PUBLIC_URL|ORTHANC_AUTHENTICATION_ENABLED)=' "$ENV_FILE"
