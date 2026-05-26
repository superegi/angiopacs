import os
import uuid
from datetime import datetime
from pathlib import Path

DATA_PATH = os.getenv("DATA_PATH", "/app/data")

def guardar_imagen(file_bytes: bytes, extension: str = "jpg") -> str:
    fecha = datetime.now().strftime("%Y-%m-%d")
    carpeta = Path(DATA_PATH) / fecha
    carpeta.mkdir(parents=True, exist_ok=True)

    nombre = f"{uuid.uuid4().hex}.{extension}"
    ruta = carpeta / nombre

    with open(ruta, "wb") as f:
        f.write(file_bytes)

    return str(ruta)
