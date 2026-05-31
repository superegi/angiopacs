#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "ERROR: no existe .env. Ejecuta ./scripts/generate_env.sh"
  exit 1
fi

set -a
source .env
set +a

python3 - <<'PY'
import json
import os
from pathlib import Path

required = [
    "ORTHANC_NAME",
    "ORTHANC_AETITLE",
    "ORTHANC_BACKEND_USER",
    "ORTHANC_BACKEND_PASSWORD",
    "ORTHANC_ADMIN_USER",
    "ORTHANC_ADMIN_PASSWORD",
    "ORTHANC_VISIT_USER",
    "ORTHANC_VISIT_PASSWORD",
]

missing = [k for k in required if not os.getenv(k)]
if missing:
    raise SystemExit("Faltan variables: " + ", ".join(missing))

auth_enabled = os.getenv("ORTHANC_AUTHENTICATION_ENABLED", "true").strip().lower() in ["1", "true", "yes", "si"]

cfg = {
    "Name": os.environ["ORTHANC_NAME"],
    "DicomAet": os.environ["ORTHANC_AETITLE"],
    "StorageDirectory": "/var/lib/orthanc/db",

    "RemoteAccessAllowed": True,
    "AuthenticationEnabled": auth_enabled,

    "RegisteredUsers": {
        os.environ["ORTHANC_BACKEND_USER"]: os.environ["ORTHANC_BACKEND_PASSWORD"],
        os.environ["ORTHANC_ADMIN_USER"]: os.environ["ORTHANC_ADMIN_PASSWORD"],
        os.environ["ORTHANC_VISIT_USER"]: os.environ["ORTHANC_VISIT_PASSWORD"],
    },

    "OrthancExplorer2": {
        "Enable": True,
        "IsDefaultOrthancUI": True
    },

    "StoneWebViewer": {
        "Enable": True
    },

    "WebViewer": {
        "Enable": True
    },

    "DicomWeb": {
        "Enable": True,
        "Root": "/dicom-web/",
        "EnableWado": True,
        "WadoRoot": "/wado"
    }
}

Path("config").mkdir(exist_ok=True)

Path("config/orthanc.json").write_text(
    json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
)

print("OK generado config/orthanc.json")
print("Usuarios Orthanc:")
print(" -", os.environ["ORTHANC_BACKEND_USER"])
print(" -", os.environ["ORTHANC_ADMIN_USER"])
print(" -", os.environ["ORTHANC_VISIT_USER"])
PY
