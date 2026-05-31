#!/usr/bin/env bash

# NeuroPACS / AngioPACS
# Exportador diagnóstico integral.
# Objetivo: generar UN solo TXT suficiente para revisar estado, compilar, validar contenedores,
# revisar BD, Git, archivos relevantes y decidir el siguiente paso sin pedir comandos sueltos.

set +e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR" || exit 1

TS="$(date +%Y%m%d_%H%M%S)"
OUT="ANGIO_DIAG_project_state_${TS}.txt"
MAX_BYTES="${MAX_BYTES:-350000}"
CMD_TIMEOUT="${CMD_TIMEOUT:-35}"

# Cargar .env solo para usar puertos/nombres. La salida se enmascara después.
if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

PORT_BACKEND_EFFECTIVE="${PORT_BACKEND:-8001}"
PORT_ORTHANC_WEB_EFFECTIVE="${PORT_ORTHANC_WEB:-8043}"
POSTGRES_USER_EFFECTIVE="${POSTGRES_USER:-admin_angio}"
POSTGRES_DB_EFFECTIVE="${POSTGRES_DB:-angiopacs_db}"
BASE_URL_EFFECTIVE="${WEB_PUBLIC_URL:-http://localhost:${PORT_BACKEND_EFFECTIVE}}"

is_text_file() {
  local f="$1"
  [ -f "$f" ] || return 1

  local size
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  [ "$size" -le "$MAX_BYTES" ] || return 1

  if file --mime "$f" 2>/dev/null | grep -qE 'charset=binary'; then
    return 1
  fi

  return 0
}

mask_env_file() {
  local f="$1"
  [ -f "$f" ] || return 0

  sed -E '
    s#^(.*PASSWORD=).*#\1***MASKED***#;
    s#^(.*SECRET=).*#\1***MASKED***#;
    s#^(.*TOKEN=).*#\1***MASKED***#;
    s#^(.*KEY=).*#\1***MASKED***#;
    s#^(DATABASE_URL=).*#\1***MASKED***#;
    s#(postgresql://[^:]+:)[^@]+(@)#\1***MASKED***\2#g;
  ' "$f"
}

mask_sensitive_stream() {
  sed -E '
    s#([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd][=:][[:space:]]*)[^[:space:]]+#\1***MASKED***#g;
    s#([Ss][Ee][Cc][Rr][Ee][Tt][=:][[:space:]]*)[^[:space:]]+#\1***MASKED***#g;
    s#([Tt][Oo][Kk][Ee][Nn][=:][[:space:]]*)[^[:space:]]+#\1***MASKED***#g;
    s#([Kk][Ee][Yy][=:][[:space:]]*)[^[:space:]]+#\1***MASKED***#g;
    s#(DATABASE_URL[:=][[:space:]]*)[^[:space:]]+#\1***MASKED***#g;
    s#(postgresql://[^:]+:)[^@]+(@)#\1***MASKED***\2#g;
    s#(ORTHANC__[A-Z_]*PASSWORD[^[:space:]]*[[:space:]]*)[^[:space:]]+#\1***MASKED***#g;
  '
}

section() {
  echo
  echo "==================== $1 ===================="
}

run_cmd() {
  echo
  echo "----- $* -----"
  local tmp rc
  tmp="$(mktemp)"
  "$@" >"$tmp" 2>&1
  rc=$?
  mask_sensitive_stream < "$tmp"
  rm -f "$tmp"
  echo "EXIT_CODE=$rc"
}

run_sh() {
  echo
  echo "----- $1 -----"
  local tmp rc
  tmp="$(mktemp)"
  bash -lc "$1" >"$tmp" 2>&1
  rc=$?
  mask_sensitive_stream < "$tmp"
  rm -f "$tmp"
  echo "EXIT_CODE=$rc"
}

run_timeout_sh() {
  echo
  echo "----- $1 -----"
  local tmp rc
  tmp="$(mktemp)"
  timeout "${CMD_TIMEOUT}s" bash -lc "$1" >"$tmp" 2>&1
  rc=$?
  mask_sensitive_stream < "$tmp"
  rm -f "$tmp"
  echo "EXIT_CODE=$rc"
}

run_docker_exec() {
  local service="$1"
  shift

  echo
  echo "----- docker compose exec -T ${service} $* -----"
  local tmp rc
  tmp="$(mktemp)"
  timeout "${CMD_TIMEOUT}s" docker compose exec -T "$service" "$@" >"$tmp" 2>&1 </dev/null
  rc=$?
  mask_sensitive_stream < "$tmp"
  rm -f "$tmp"
  echo "EXIT_CODE=$rc"
}

http_check() {
  local label="$1"
  local url="$2"
  local body="/tmp/angio_http_${label//[^a-zA-Z0-9]/_}.txt"
  local code

  echo
  echo "----- HTTP ${label}: ${url} -----"
  code="$(curl -k -s --max-time 8 -o "$body" -w "%{http_code}" "$url" 2>/tmp/angio_http_err.txt)"
  local rc=$?
  echo "HTTP_CODE=${code}"
  echo "CURL_EXIT_CODE=${rc}"

  if [ -s /tmp/angio_http_err.txt ]; then
    echo "--- curl stderr ---"
    cat /tmp/angio_http_err.txt
  fi

  echo "--- body first 1000 bytes ---"
  head -c 1000 "$body" 2>/dev/null || true
  echo
}

{
echo "============================================================"
echo "ANGIOPACS / NEUROPACS - PROJECT STATE EXPORT COMPLETO"
echo "Fecha: $(date)"
echo "Host: $(hostname)"
echo "Usuario: $(whoami)"
echo "Ruta: $(pwd)"
echo "Archivo: $OUT"
echo "MAX_BYTES por archivo: $MAX_BYTES"
echo "CMD_TIMEOUT: ${CMD_TIMEOUT}s"
echo "BASE_URL_EFFECTIVE: ${BASE_URL_EFFECTIVE}"
echo "PORT_BACKEND_EFFECTIVE: ${PORT_BACKEND_EFFECTIVE}"
echo "PORT_ORTHANC_WEB_EFFECTIVE: ${PORT_ORTHANC_WEB_EFFECTIVE}"
echo "POSTGRES_DB_EFFECTIVE: ${POSTGRES_DB_EFFECTIVE}"
echo "============================================================"

section "RESUMEN EJECUTIVO AUTOMATICO"

echo "Objetivo: este bloque resume si se puede avanzar sin pedir comandos adicionales."
echo

echo "----- Git dirty summary -----"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git status --short
  if [ -z "$(git status --short)" ]; then
    echo "GIT_STATUS=clean"
  else
    echo "GIT_STATUS=dirty"
  fi

  echo
  echo "----- Git untracked no ignorados -----"
  git ls-files --others --exclude-standard | sort

  echo
  echo "----- Directorios backup locales detectados -----"
  find . -maxdepth 1 -type d -name 'backups_*' -print | sort
else
  echo "No es repositorio Git."
fi

echo
echo "----- Docker compose ps compacto -----"
docker compose ps 2>&1 | mask_sensitive_stream || true

echo
echo "----- HTTP readiness retry /health -----"
for i in 1 2 3 4 5; do
  code="$(curl -k -s --max-time 5 -o /tmp/angio_health_retry.txt -w "%{http_code}" "http://localhost:${PORT_BACKEND_EFFECTIVE}/health" 2>/tmp/angio_health_retry.err)"
  rc=$?
  echo "try=${i} HTTP_CODE=${code} CURL_EXIT_CODE=${rc}"
  head -c 200 /tmp/angio_health_retry.txt 2>/dev/null || true
  echo
  [ "$code" = "200" ] && break
  sleep 1
done

echo
echo "----- Python compile host summary -----"
python3 -m py_compile \
  backend/main.py \
  backend/models.py \
  backend/routers/usuarios.py \
  backend/routers/pacientes.py \
  backend/db/migrations.py 2>&1
echo "HOST_PY_COMPILE_EXIT_CODE=$?"

echo
echo "----- Python compile container summary -----"
timeout "${CMD_TIMEOUT}s" docker compose exec -T backend-bot python -m py_compile \
  /app/main.py \
  /app/models.py \
  /app/routers/usuarios.py \
  /app/routers/pacientes.py \
  /app/db/migrations.py </dev/null 2>&1
echo "CONTAINER_PY_COMPILE_EXIT_CODE=$?"

echo
echo "----- Usuarios columnas críticas summary -----"
docker compose exec -T postgres-db psql \
  -U "${POSTGRES_USER_EFFECTIVE}" \
  -d "${POSTGRES_DB_EFFECTIVE}" \
  -Atc "
SELECT
  'has_debe_cambiar_password=' || EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='usuarios' AND column_name='debe_cambiar_password'
  );
SELECT
  'has_password_temporal=' || EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='usuarios' AND column_name='password_temporal'
  );
SELECT
  'has_ultimo_login_en=' || EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='usuarios' AND column_name='ultimo_login_en'
  );
SELECT
  'has_ultimo_login_ip=' || EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='usuarios' AND column_name='ultimo_login_ip'
  );
SELECT
  'has_perfil_actualizado_en=' || EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='usuarios' AND column_name='perfil_actualizado_en'
  );
" </dev/null 2>&1 | mask_sensitive_stream

section "MAQUINA LOCAL"
run_cmd hostnamectl
run_cmd uname -a
run_cmd lsb_release -a
run_cmd whoami
run_cmd id
run_cmd pwd
run_cmd df -h .
run_cmd free -h

section "TREE DEL PROYECTO"
if command -v tree >/dev/null 2>&1; then
  tree -a \
    -I '.git|.env|.env.*|config/orthanc.json|orthanc-storage|fotos_pacientes|__pycache__|*.pyc|*.bak_*|*.bak.*|ANGIO_DIAG_*|*.tar.gz|*.zip|*.dcm|*.ima|*.sqlite|*.db|node_modules|postgres_data|data|volumes|storage|backups_*' \
    .
else
  find . \
    -path './.git' -prune -o \
    -path './orthanc-storage' -prune -o \
    -path './fotos_pacientes' -prune -o \
    -path './__pycache__' -prune -o \
    -path './backups_*' -prune -o \
    -name 'ANGIO_DIAG_*' -prune -o \
    -print | sort
fi

section "ESTRUCTURA ENFOCADA PARA DESARROLLO"
echo "Objetivo: vista rápida de archivos relevantes para editar código."

echo
echo "----- tree backend -L 3 -----"
tree backend -L 3 2>/dev/null || find backend -maxdepth 3 -print | sort

echo
echo "----- tree backend/templates -L 2 -----"
tree backend/templates -L 2 2>/dev/null || find backend/templates -maxdepth 2 -print | sort

echo
echo "----- tree backend/db -L 2 -----"
tree backend/db -L 2 2>/dev/null || find backend/db -maxdepth 2 -print | sort

echo
echo "----- tree docs -L 2 -----"
tree docs -L 2 2>/dev/null || find docs -maxdepth 2 -print | sort

echo
echo "----- tree scripts -L 2 -----"
tree scripts -L 2 2>/dev/null || find scripts -maxdepth 2 -print | sort

section "ARCHIVOS CLAVE PARA USUARIOS Y LOGIN"
for f in \
  backend/models.py \
  backend/main.py \
  backend/routers/usuarios.py \
  backend/templates/login.html \
  backend/templates/usuarios.html \
  backend/templates/mi_perfil.html \
  backend/templates/_sidebar.html \
  backend/db/migrations.py \
  backend/static/css/style.css
do
  echo
  echo "============================================================"
  echo "FILE CLAVE: $f"
  echo "============================================================"
  if [ -f "$f" ]; then
    sed -n '1,360p' "$f"
  else
    echo "No existe"
  fi
done

section "RUTAS FASTAPI DETECTADAS"
grep -RInE '^[[:space:]]*@.*\.(get|post|put|delete|patch)\(' backend/*.py backend/routers/*.py 2>/dev/null || true

section "CLASES SQLALCHEMY DETECTADAS"
grep -nE '^class ' backend/models.py 2>/dev/null || true

section "GREP FUNCIONALIDADES CRITICAS"
echo "----- Seguridad usuarios -----"
grep -RInE 'debe_cambiar_password|password_temporal|ultimo_login|perfil_actualizado|mi-perfil|reset-password|must_change_password|enforce_password_change' backend 2>/dev/null || true

echo
echo "----- Auditoria / logs -----"
grep -RInE 'AuditoriaEvento|auditoria_eventos|registrar_evento|log general|actividad|client_timezone|client_utc_offset' backend 2>/dev/null || true

echo
echo "----- DICOM / Orthanc, solo referencia; no reparar aqui -----"
grep -RInE 'StudyInstanceUID|study_instance_uid|orthanc|dicom|ZIP|zipfile|reintentar|subir_dicom' backend/routers backend/services backend/*.py 2>/dev/null || true

section "GIT INFO"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  run_cmd git branch --show-current
  run_cmd git branch -vv
  run_cmd git remote -v
  run_cmd git rev-parse HEAD
  run_cmd git status --short
  run_cmd git status --ignored --short
  run_cmd git ls-files --others --exclude-standard
  run_cmd git log --oneline -n 40
  run_cmd git tag --sort=-creatordate
  run_cmd git diff --stat
  run_cmd git diff --cached --stat
  run_cmd git diff --name-status
  run_cmd git diff --cached --name-status
  run_cmd git diff --check
  run_cmd git diff --cached --check

  echo
  echo "----- git diff completo, archivos versionables modificados -----"
  git diff --color=never 2>&1 | mask_sensitive_stream || true

  echo
  echo "----- git diff staged completo -----"
  git diff --cached --color=never 2>&1 | mask_sensitive_stream || true
else
  echo "No es repositorio Git."
fi

section "DOCKER INFO"
if command -v docker >/dev/null 2>&1; then
  run_cmd docker version
  run_cmd docker compose version
  run_cmd docker compose ps

  echo
  echo "----- docker inspect backend estado -----"
  docker inspect angio_backend_bot \
    --format 'Status={{.State.Status}} Restarting={{.State.Restarting}} ExitCode={{.State.ExitCode}} Error={{.State.Error}} StartedAt={{.State.StartedAt}} FinishedAt={{.State.FinishedAt}}' 2>&1 || true

  echo
  echo "----- docker inspect postgres estado -----"
  docker inspect angio_db \
    --format 'Status={{.State.Status}} Restarting={{.State.Restarting}} ExitCode={{.State.ExitCode}} Error={{.State.Error}} StartedAt={{.State.StartedAt}} FinishedAt={{.State.FinishedAt}}' 2>&1 || true

  echo
  echo "----- docker inspect orthanc estado -----"
  docker inspect angio_pacs \
    --format 'Status={{.State.Status}} Restarting={{.State.Restarting}} ExitCode={{.State.ExitCode}} Error={{.State.Error}} StartedAt={{.State.StartedAt}} FinishedAt={{.State.FinishedAt}}' 2>&1 || true

  run_cmd docker images

  echo
  echo "----- docker compose config sanitizado -----"
  docker compose config 2>&1 | mask_sensitive_stream || true

  section "DOCKER HOST-CONTENEDOR HASH CHECK"
  FILES_SYNC="
main.py
models.py
routers/usuarios.py
routers/pacientes.py
db/migrations.py
templates/login.html
templates/usuarios.html
templates/mi_perfil.html
templates/_sidebar.html
static/css/style.css
"
  for f in $FILES_SYNC; do
    host_file="backend/$f"
    cont_file="/app/$f"

    echo
    echo "--- $f ---"
    if [ ! -f "$host_file" ]; then
      echo "HOST: NO_EXISTE"
      continue
    fi

    host_hash="$(sha256sum "$host_file" | awk '{print $1}')"
    cont_hash="$(timeout "${CMD_TIMEOUT}s" docker compose exec -T backend-bot sh -lc "sha256sum '$cont_file' 2>/dev/null | awk '{print \$1}'" </dev/null 2>/dev/null)"

    echo "HOST_HASH=${host_hash}"
    echo "CONTAINER_HASH=${cont_hash:-NO_EXISTE}"

    if [ "$host_hash" = "$cont_hash" ]; then
      echo "SYNC=OK"
    else
      echo "SYNC=WARN_DISTINTO"
    fi
  done

  section "PYTHON COMPILE"
  run_cmd python3 -m py_compile \
    backend/main.py \
    backend/models.py \
    backend/routers/usuarios.py \
    backend/routers/pacientes.py \
    backend/db/migrations.py

  run_docker_exec backend-bot python -m py_compile \
    /app/main.py \
    /app/models.py \
    /app/routers/usuarios.py \
    /app/routers/pacientes.py \
    /app/db/migrations.py

  section "LOGS DOCKER"
  run_cmd docker compose logs --tail=180 backend-bot
  run_cmd docker compose logs --tail=120 orthanc-pacs
  run_cmd docker compose logs --tail=120 postgres-db
else
  echo "Docker no disponible."
fi

section "PUERTOS Y RED LOCAL"
run_cmd ss -ltnp
run_cmd ip -br addr
run_cmd ip route

section "HEALTH CHECKS HTTP CON RETRY"
echo "Base usada: http://localhost:${PORT_BACKEND_EFFECTIVE}"
for i in 1 2 3 4 5; do
  echo
  echo "----- intento $i /health -----"
  curl -k -s --max-time 5 -o /tmp/angio_check_health.txt -w "HTTP %{http_code}\n" "http://localhost:${PORT_BACKEND_EFFECTIVE}/health" 2>&1 || true
  head -c 500 /tmp/angio_check_health.txt 2>/dev/null || true
  echo
  sleep 1
done

http_check "backend_health" "http://localhost:${PORT_BACKEND_EFFECTIVE}/health"
http_check "backend_login" "http://localhost:${PORT_BACKEND_EFFECTIVE}/login"
http_check "backend_root" "http://localhost:${PORT_BACKEND_EFFECTIVE}/"
http_check "backend_usuarios" "http://localhost:${PORT_BACKEND_EFFECTIVE}/usuarios"
http_check "backend_mi_perfil" "http://localhost:${PORT_BACKEND_EFFECTIVE}/mi-perfil"
http_check "backend_repositorios" "http://localhost:${PORT_BACKEND_EFFECTIVE}/repositorios"
http_check "backend_auditoria" "http://localhost:${PORT_BACKEND_EFFECTIVE}/auditoria"
http_check "orthanc_direct_system" "http://localhost:${PORT_ORTHANC_WEB_EFFECTIVE}/system"

section "POSTGRES DIAGNOSTICO COMPLETO"
if command -v docker >/dev/null 2>&1; then
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "\dt"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "\d usuarios"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "\d procedimientos"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "\d auditoria_eventos"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "\d estudios_dicom"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "SELECT COUNT(*) AS usuarios_count FROM usuarios;"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "SELECT id, username, nombre, mail, especialidad, rol, activo, debe_cambiar_password, password_temporal, ultimo_login_en, ultimo_login_ip FROM usuarios ORDER BY id;"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "SELECT COUNT(*) AS procedimientos_count FROM procedimientos;"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "SELECT COUNT(*) AS auditoria_count FROM auditoria_eventos;"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "SELECT id, creado_en, usuario, accion, tarea, estado, caso_id, archivo_nombre, client_timezone, client_utc_offset_minutes FROM auditoria_eventos ORDER BY id DESC LIMIT 25;"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "SELECT COUNT(*) AS estudios_dicom_count FROM estudios_dicom;"
  run_docker_exec postgres-db psql -U "${POSTGRES_USER_EFFECTIVE}" -d "${POSTGRES_DB_EFFECTIVE}" -c "SELECT study_instance_uid, COUNT(*) FROM estudios_dicom GROUP BY study_instance_uid HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC LIMIT 20;"
fi

section "TAMAÑO DE CARPETAS RELEVANTES"
du -sh . 2>/dev/null || true
du -sh backend config docs scripts 2>/dev/null || true
find . -maxdepth 3 -type d \( -name data -o -name volumes -o -name storage -o -name orthanc-storage -o -name postgres_data -o -name 'backups_*' \) -print -exec du -sh {} \; 2>/dev/null || true

section "ENV LOCAL SANITIZADO"
if [ -f ".env" ]; then
  echo "Archivo .env existe. Valores sensibles enmascarados:"
  mask_env_file ".env"
else
  echo "No existe .env"
fi

section "ARCHIVOS VERSIONABLES Y NUEVOS"
echo "Fuente: git ls-files -co --exclude-standard"
echo "Nota: se excluyen secretos, datos, binarios, backups y archivos grandes."

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  FILES="$(git ls-files -co --exclude-standard | sort)"
else
  FILES="$(find . -type f | sed 's#^\./##' | sort)"
fi

while IFS= read -r f; do
  [ -z "$f" ] && continue

  case "$f" in
    .env|.env.*|config/orthanc.json|ANGIO_DIAG_*|*.bak_*|*.bak.*|*.tar.gz|*.zip|*.dcm|*.ima|*.png|*.jpg|*.jpeg|*.gif|*.webp|*.pdf|*.db|*.sqlite)
      continue
      ;;
    backups_*|backups_*/*|orthanc-storage/*|fotos_pacientes/*|.git/*|__pycache__/*|*/__pycache__/*|data/*|volumes/*|storage/*|postgres_data/*)
      continue
      ;;
  esac

  if is_text_file "$f"; then
    echo
    echo "============================================================"
    echo "FILE: $f"
    echo "============================================================"
    sed -n '1,5000p' "$f" | mask_sensitive_stream
  else
    echo
    echo "============================================================"
    echo "FILE OMITIDO: $f"
    echo "Motivo: binario, no existe, o supera MAX_BYTES=$MAX_BYTES"
    echo "============================================================"
    ls -lh "$f" 2>/dev/null || true
    file "$f" 2>/dev/null || true
  fi
done <<< "$FILES"

section "CRITERIOS RAPIDOS PARA DECIDIR COMMIT"
echo "OK para commit local si:"
echo "1) /health retorna HTTP 200."
echo "2) Python compile host y contenedor tienen EXIT_CODE=0."
echo "3) Las columnas esperadas existen en la BD."
echo "4) git diff --check no muestra errores."
echo "5) No hay backups_* ni secretos como archivos untracked a commitear."
echo "6) git status contiene solo archivos esperados para el cambio actual."

section "FIN EXPORT"
} > "$OUT" 2>&1

echo "Archivo generado:"
echo "$OUT"
ls -lh "$OUT"

echo
echo "#######################################"
echo "######    FIN INPUT    ###############"
echo "#######################################"
