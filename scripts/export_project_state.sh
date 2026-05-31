#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TS="$(date +%Y%m%d_%H%M%S)"
OUT="ANGIO_DIAG_project_state_${TS}.txt"

MAX_BYTES="${MAX_BYTES:-250000}"

is_text_file() {
  local f="$1"

  if [ ! -f "$f" ]; then
    return 1
  fi

  # evitar archivos grandes
  local size
  size=$(stat -c%s "$f" 2>/dev/null || echo 0)
  if [ "$size" -gt "$MAX_BYTES" ]; then
    return 1
  fi

  # evitar binarios
  if file --mime "$f" 2>/dev/null | grep -qE 'charset=binary'; then
    return 1
  fi

  return 0
}

mask_env_file() {
  local f="$1"

  if [ ! -f "$f" ]; then
    return 0
  fi

  sed -E '
    s#^(.*PASSWORD=).*#\1***MASKED***#;
    s#^(.*SECRET=).*#\1***MASKED***#;
    s#^(.*TOKEN=).*#\1***MASKED***#;
    s#^(.*KEY=).*#\1***MASKED***#;
    s#^(DATABASE_URL=).*#\1***MASKED***#;
  ' "$f"
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

echo
echo "==================== TREE DEL PROYECTO ===================="
if command -v tree >/dev/null 2>&1; then
  tree -a \
    -I '.git|.env|config/orthanc.json|orthanc-storage|fotos_pacientes|__pycache__|*.pyc|*.bak_*|ANGIO_DIAG_*|*.tar.gz|*.zip|*.dcm|*.ima|*.sqlite|*.db|node_modules|postgres_data' \
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

echo
echo "==================== GIT INFO ===================="
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo
  echo "----- git branch -----"
  git branch --show-current || true

  echo
  echo "----- git remote -v -----"
  git remote -v || true

  echo
  echo "----- git status --short -----"
  git status --short || true

  echo
  echo "----- git log --oneline -n 20 -----"
  git log --oneline -n 20 || true

  echo
  echo "----- git tag --sort=-creatordate | head -20 -----"
  git tag --sort=-creatordate | head -20 || true

  echo
  echo "----- git diff --stat -----"
  git diff --stat || true

  echo
  echo "----- git diff --cached --stat -----"
  git diff --cached --stat || true
else
  echo "No es repositorio Git."
fi

echo
echo "==================== DOCKER INFO ===================="
if command -v docker >/dev/null 2>&1; then
  echo
  echo "----- docker compose ps -----"
  docker compose ps 2>/dev/null || sudo docker compose ps 2>/dev/null || true

  echo
  echo "----- docker images relevantes -----"
  docker images | grep -Ei 'angiopacs|orthanc|postgres' || true

  echo
  echo "----- logs backend tail 80 -----"
  docker compose logs --tail=80 backend-bot 2>/dev/null || sudo docker compose logs --tail=80 backend-bot 2>/dev/null || true

  echo
  echo "----- logs orthanc tail 80 -----"
  docker compose logs --tail=80 orthanc-pacs 2>/dev/null || sudo docker compose logs --tail=80 orthanc-pacs 2>/dev/null || true
else
  echo "Docker no disponible."
fi

echo
echo "==================== ENV LOCAL SANITIZADO ===================="
if [ -f ".env" ]; then
  echo "Archivo .env existe. Valores sensibles enmascarados:"
  mask_env_file ".env"
else
  echo "No existe .env"
fi

echo
echo "==================== ARCHIVOS VERSIONABLES ===================="
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
    orthanc-storage/*|fotos_pacientes/*|.git/*|__pycache__/*)
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

echo
echo "==================== FIN EXPORT ===================="
} > "$OUT" 2>&1

echo "Archivo generado:"
echo "$OUT"
ls -lh "$OUT"
