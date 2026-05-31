#!/usr/bin/env bash

cd "$(dirname "$0")/.."

TS="$(date +%Y%m%d_%H%M%S)"
OUT="ANGIO_DIAG_project_state_${TS}.txt"
MAX_BYTES="${MAX_BYTES:-250000}"

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
  '
}

section() {
  echo
  echo "==================== $1 ===================="
}

run_cmd() {
  echo
  echo "----- $* -----"
  "$@" 2>&1 || true
}

{
echo "============================================================"
echo "ANGIOPACS / NEUROPACS - PROJECT STATE EXPORT"
echo "Fecha: $(date)"
echo "Host: $(hostname)"
echo "Usuario: $(whoami)"
echo "Ruta: $(pwd)"
echo "Archivo: $OUT"
echo "MAX_BYTES por archivo: $MAX_BYTES"
echo "============================================================"

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
    -I '.git|.env|config/orthanc.json|orthanc-storage|fotos_pacientes|__pycache__|*.pyc|*.bak_*|ANGIO_DIAG_*|*.tar.gz|*.zip|*.dcm|*.ima|*.sqlite|*.db|node_modules|postgres_data|data|volumes|storage' \
    .
else
  find . \
    -path './.git' -prune -o \
    -path './orthanc-storage' -prune -o \
    -path './fotos_pacientes' -prune -o \
    -path './__pycache__' -prune -o \
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

section "ARCHIVOS CLAVE PARA USUARIOS Y LOGIN"
for f in \
  backend/models.py \
  backend/main.py \
  backend/routers/usuarios.py \
  backend/templates/login.html \
  backend/templates/usuarios.html \
  backend/templates/_sidebar.html \
  backend/db/migrations.py
do
  echo
  echo "============================================================"
  echo "FILE CLAVE: $f"
  echo "============================================================"
  if [ -f "$f" ]; then
    sed -n '1,260p' "$f"
  else
    echo "No existe"
  fi
done

section "RUTAS FASTAPI DETECTADAS"
grep -RInE '^[[:space:]]*@.*\.(get|post|put|delete|patch)\(' backend/*.py backend/routers/*.py 2>/dev/null || true

section "CLASES SQLALCHEMY DETECTADAS"
grep -nE '^class ' backend/models.py 2>/dev/null || true


section "GIT INFO"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  run_cmd git branch --show-current
  run_cmd git branch -vv
  run_cmd git remote -v
  run_cmd git rev-parse HEAD
  run_cmd git status --short
  run_cmd git status --ignored --short
  run_cmd git ls-files --others --exclude-standard
  run_cmd git log --oneline -n 30
  run_cmd git tag --sort=-creatordate
  run_cmd git diff --stat
  run_cmd git diff --cached --stat
else
  echo "No es repositorio Git."
fi

section "DOCKER INFO"
if command -v docker >/dev/null 2>&1; then
  run_cmd docker version
  run_cmd docker compose version
  run_cmd docker compose ps
  run_cmd docker images
  echo
  echo "----- docker compose config sanitizado -----"
  docker compose config 2>&1 | mask_sensitive_stream || true
  run_cmd docker compose logs --tail=120 backend-bot
  run_cmd docker compose logs --tail=120 orthanc-pacs
  run_cmd docker compose logs --tail=80 postgres-db
else
  echo "Docker no disponible."
fi

section "PUERTOS Y RED LOCAL"
run_cmd ss -ltnp
run_cmd ip -br addr
run_cmd ip route

section "HEALTH CHECKS HTTP"
for url in \
  "http://localhost:${PORT_BACKEND:-8001}/health" \
  "http://localhost:${PORT_BACKEND:-8001}/login" \
  "http://localhost:${PORT_BACKEND:-8001}/" \
  "http://localhost:${PORT_BACKEND:-8001}/usuarios" \
  "http://localhost:${PORT_BACKEND:-8001}/repositorios" \
  "http://localhost:${PORT_BACKEND:-8001}/auditoria" \
  "http://localhost:${PORT_ORTHANC_WEB:-8043}/system"
do
  echo
  echo "----- $url -----"
  curl -k -s -o /tmp/angio_check_body.txt -w "HTTP %{http_code}\n" "$url" 2>&1 || true
  head -c 500 /tmp/angio_check_body.txt 2>/dev/null || true
  echo
done

section "POSTGRES DIAGNOSTICO BASICO"
if command -v docker >/dev/null 2>&1; then
  docker compose exec -T postgres-db psql -U "${POSTGRES_USER:-admin_angio}" -d "${POSTGRES_DB:-angiopacs_db}" -c "\dt" 2>&1 || true
  docker compose exec -T postgres-db psql -U "${POSTGRES_USER:-admin_angio}" -d "${POSTGRES_DB:-angiopacs_db}" -c "\d usuarios" 2>&1 || true
  docker compose exec -T postgres-db psql -U "${POSTGRES_USER:-admin_angio}" -d "${POSTGRES_DB:-angiopacs_db}" -c "\d procedimientos" 2>&1 || true
fi

section "TAMAÑO DE CARPETAS RELEVANTES"
du -sh . 2>/dev/null || true
du -sh backend config docs scripts 2>/dev/null || true
find . -maxdepth 3 -type d \( -name data -o -name volumes -o -name storage -o -name orthanc-storage -o -name postgres_data \) -print -exec du -sh {} \; 2>/dev/null || true

section "ENV LOCAL SANITIZADO"
if [ -f ".env" ]; then
  echo "Archivo .env existe. Valores sensibles enmascarados:"
  mask_env_file ".env"
else
  echo "No existe .env"
fi

section "ARCHIVOS VERSIONABLES"
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
    .env|config/orthanc.json|ANGIO_DIAG_*|*.bak_*|*.tar.gz|*.zip|*.dcm|*.ima|*.png|*.jpg|*.jpeg|*.gif|*.webp|*.pdf|*.db|*.sqlite)
      continue
      ;;
    orthanc-storage/*|fotos_pacientes/*|.git/*|__pycache__/*|data/*|volumes/*|storage/*|postgres_data/*)
      continue
      ;;
  esac

  if is_text_file "$f"; then
    echo
    echo "============================================================"
    echo "FILE: $f"
    echo "============================================================"
    sed -n '1,4000p' "$f"
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

section "FIN EXPORT"
} > "$OUT" 2>&1

echo "Archivo generado:"
echo "$OUT"
ls -lh "$OUT"

echo
echo "#######################################"
echo "######    FIN INPUT    ###############"
echo "#######################################"
