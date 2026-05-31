#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ENV_EXAMPLE=".env.example"
ENV_FILE=".env"
CREDENTIALS_FILE=".env.credentials.txt"

RED="$(printf '\033[31m')"
GREEN="$(printf '\033[32m')"
YELLOW="$(printf '\033[33m')"
BOLD="$(printf '\033[1m')"
RESET="$(printf '\033[0m')"

rand_hex() {
  openssl rand -hex "${1:-24}"
}

usage() {
  cat <<EOF
Uso:
  scripts/generate_env.sh [opciones]

Comportamiento estándar:
  - Si NO existe .env: abre wizard interactivo.
  - Si existe .env: advierte en rojo y pregunta si quieres sobrescribir.
  - Genera claves seguras y las muestra/guarda para el primer ingreso.

Opciones:
  --force        Sobrescribe .env sin preguntar.
  --keep         Si .env existe, no lo modifica.
  -h, --help     Muestra ayuda.
EOF
}

FORCE=0
KEEP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    --keep)
      KEEP=1
      shift
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

if [[ -f "$ENV_FILE" && "$KEEP" -eq 1 ]]; then
  echo "OK: $ENV_FILE existe. No se modifica."
  exit 0
fi

if [[ -f "$ENV_FILE" && "$FORCE" -ne 1 ]]; then
  echo
  echo "${RED}${BOLD}ADVERTENCIA: ya existe .env.${RESET}"
  echo "${YELLOW}Sobrescribirlo generará nuevas claves y puede desconectar la base de datos/Orthanc actuales.${RESET}"
  echo
  read -rp "¿Quieres sobrescribir .env? Escribe SI para continuar: " CONFIRMAR

  if [[ "$CONFIRMAR" != "SI" ]]; then
    echo "OK: se conserva .env actual."
    exit 0
  fi
fi

if [[ -f "$ENV_FILE" ]]; then
  BACKUP=".env.backup_$(date +%F_%H%M%S)"
  cp "$ENV_FILE" "$BACKUP"
  chmod 600 "$BACKUP"
  echo "Backup creado: $BACKUP"
fi

umask 077
cp "$ENV_EXAMPLE" "$ENV_FILE"
chmod 600 "$ENV_FILE"

set_kv() {
  local key="$1"
  local val="$2"

  python3 - "$ENV_FILE" "$key" "$val" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
val = sys.argv[3]

lines = path.read_text().splitlines()
out = []
found = False

for line in lines:
    if line.startswith(f"{key}="):
        out.append(f"{key}={val}")
        found = True
    else:
        out.append(line)

if not found:
    out.append(f"{key}={val}")

path.write_text("\n".join(out) + "\n")
PY
}

prompt_default() {
  local label="$1"
  local current="$2"
  local value=""

  read -rp "${label} [${current}]: " value
  if [[ -n "$value" ]]; then
    echo "$value"
  else
    echo "$current"
  fi
}

prompt_secret_generated() {
  local label="$1"
  local generated="$2"
  local value=""

  read -rsp "${label} [Enter = usar clave generada]: " value
  echo >&2

  if [[ -n "$value" ]]; then
    echo "$value"
  else
    echo "$generated"
  fi
}

echo
echo "${BOLD}Wizard de configuración AngioPACS / NeuroPACS${RESET}"
echo "Presiona Enter para aceptar el valor sugerido."
echo

# Defaults seguros/generales
POSTGRES_USER="admin_angio"
POSTGRES_DB="angiopacs_db"

ANGIOPACS_USER="admin"
ANGIOPACS_PASSWORD_GENERATED="$(rand_hex 16)"
ANGIOPACS_SESSION_SECRET="$(rand_hex 32)"

POSTGRES_PASSWORD="$(rand_hex 24)"

ORTHANC_BACKEND_USER="angio_backend"
ORTHANC_BACKEND_PASSWORD="$(rand_hex 24)"

ORTHANC_ADMIN_USER="admin_orthanc"
ORTHANC_ADMIN_PASSWORD_GENERATED="$(rand_hex 24)"

ORTHANC_VISIT_USER="visita"
ORTHANC_VISIT_PASSWORD="$(rand_hex 24)"

PORT_BACKEND_DEFAULT="8000"
PORT_ORTHANC_WEB_DEFAULT="8042"
PORT_ORTHANC_DICOM_DEFAULT="4242"

ANGIOPACS_USER="$(prompt_default "Usuario admin web inicial" "$ANGIOPACS_USER")"
ANGIOPACS_PASSWORD="$(prompt_secret_generated "Clave admin web inicial" "$ANGIOPACS_PASSWORD_GENERATED")"

echo
read -rp "Token Telegram [vacío si no lo usarás ahora]: " TELEGRAM_TOKEN

echo
PORT_BACKEND="$(prompt_default "Puerto host web FastAPI" "$PORT_BACKEND_DEFAULT")"
PORT_ORTHANC_WEB="$(prompt_default "Puerto host Orthanc Web" "$PORT_ORTHANC_WEB_DEFAULT")"
PORT_ORTHANC_DICOM="$(prompt_default "Puerto host Orthanc DICOM" "$PORT_ORTHANC_DICOM_DEFAULT")"

echo
echo "Bind Orthanc:"
echo "  127.0.0.1 = más seguro, solo local en este servidor."
echo "  0.0.0.0   = accesible desde red/VPN/Traefik. Úsalo si Traefik está en otro servidor."
ORTHANC_BIND_ADDRESS="$(prompt_default "Bind Orthanc en host" "127.0.0.1")"

echo
WEB_PUBLIC_URL_DEFAULT="http://localhost:${PORT_BACKEND}"
ORTHANC_PUBLIC_URL_DEFAULT="http://localhost:${PORT_ORTHANC_WEB}"

WEB_PUBLIC_URL="$(prompt_default "URL pública web AngioPACS" "$WEB_PUBLIC_URL_DEFAULT")"
ANGIOPACS_PUBLIC_URL="$WEB_PUBLIC_URL"
ORTHANC_PUBLIC_URL="$(prompt_default "URL pública Orthanc" "$ORTHANC_PUBLIC_URL_DEFAULT")"

echo
ORTHANC_ADMIN_USER="$(prompt_default "Usuario admin Orthanc" "$ORTHANC_ADMIN_USER")"
ORTHANC_ADMIN_PASSWORD="$(prompt_secret_generated "Clave admin Orthanc" "$ORTHANC_ADMIN_PASSWORD_GENERATED")"

# Escritura de variables
set_kv TZ "America/Santiago"

set_kv POSTGRES_USER "$POSTGRES_USER"
set_kv POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
set_kv POSTGRES_DB "$POSTGRES_DB"

set_kv PORT_BACKEND "$PORT_BACKEND"

set_kv ANGIOPACS_USER "$ANGIOPACS_USER"
set_kv ANGIOPACS_PASSWORD "$ANGIOPACS_PASSWORD"
set_kv ANGIOPACS_SESSION_SECRET "$ANGIOPACS_SESSION_SECRET"
set_kv ANGIOPACS_BOOTSTRAP_ADMIN "true"

set_kv TELEGRAM_TOKEN "$TELEGRAM_TOKEN"

set_kv PORT_ORTHANC_WEB "$PORT_ORTHANC_WEB"
set_kv PORT_ORTHANC_DICOM "$PORT_ORTHANC_DICOM"
set_kv ORTHANC_BIND_ADDRESS "$ORTHANC_BIND_ADDRESS"

set_kv ORTHANC_NAME "NeuroPACS"
set_kv ORTHANC_AETITLE "ORTHANC"
set_kv ORTHANC_URL "http://orthanc-pacs:8042"
set_kv ORTHANC_PUBLIC_URL "$ORTHANC_PUBLIC_URL"
set_kv ORTHANC_AUTHENTICATION_ENABLED "true"

set_kv ORTHANC_BACKEND_USER "$ORTHANC_BACKEND_USER"
set_kv ORTHANC_BACKEND_PASSWORD "$ORTHANC_BACKEND_PASSWORD"

set_kv ORTHANC_ADMIN_USER "$ORTHANC_ADMIN_USER"
set_kv ORTHANC_ADMIN_PASSWORD "$ORTHANC_ADMIN_PASSWORD"

set_kv ORTHANC_VISIT_USER "$ORTHANC_VISIT_USER"
set_kv ORTHANC_VISIT_PASSWORD "$ORTHANC_VISIT_PASSWORD"

# Compatibilidad con código actual
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

echo
echo "${GREEN}${BOLD}OK: $ENV_FILE generado.${RESET}"
echo "${GREEN}OK: credenciales guardadas en $CREDENTIALS_FILE${RESET}"
echo
echo "${BOLD}Credenciales iniciales para primer ingreso:${RESET}"
echo
echo "WEB AngioPACS:"
echo "  URL:     ${WEB_PUBLIC_URL}"
echo "  Usuario: ${ANGIOPACS_USER}"
echo "  Clave:   ${ANGIOPACS_PASSWORD}"
echo
echo "Orthanc admin:"
echo "  URL:     ${ORTHANC_PUBLIC_URL}"
echo "  Usuario: ${ORTHANC_ADMIN_USER}"
echo "  Clave:   ${ORTHANC_ADMIN_PASSWORD}"
echo
echo "Variables principales:"
grep -E '^(PORT_BACKEND|PORT_ORTHANC_WEB|PORT_ORTHANC_DICOM|ORTHANC_BIND_ADDRESS|WEB_PUBLIC_URL|ANGIOPACS_PUBLIC_URL|ORTHANC_PUBLIC_URL|ORTHANC_AUTHENTICATION_ENABLED)=' "$ENV_FILE"
