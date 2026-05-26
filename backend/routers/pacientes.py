from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
import uuid
import os
import zipfile


from database import get_db
from models import Procedimiento, Archivo

router = APIRouter()
templates = Jinja2Templates(directory="templates")

DATA_PATH = os.getenv("DATA_PATH", "/app/data")


@router.get("/procedimientos")
def listar_procedimientos(db: Session = Depends(get_db)):
    return db.query(Procedimiento).order_by(Procedimiento.id.desc()).all()


@router.get("/procedimientos/{procedimiento_id}")
def ver_procedimiento(
    procedimiento_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    archivos = (
        db.query(Archivo)
        .filter(Archivo.procedimiento_id == procedimiento_id)
        .order_by(Archivo.tipo.asc(), Archivo.id.asc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="procedimiento_detalle.html",
        context={
            "procedimiento": procedimiento,
            "archivos": archivos,
        }
    )


@router.post("/procedimientos/{procedimiento_id}/editar")
async def editar_procedimiento(
    procedimiento_id: int,
    lugar: str = Form(None),
    historia_clinica: str = Form(None),
    paciente_nombre: str = Form(None),
    edad: str = Form(None),
    procedimiento_txt: str = Form(None),
    diagnostico: str = Form(None),
    localizacion_aneurisma: str = Form(None),
    primer_operador: str = Form(None),
    segundo_operador: str = Form(None),
    fellow: str = Form(None),
    presentacion_clinica: str = Form(None),
    vaina: str = Form(None),
    cateter: str = Form(None),
    cateter_intermedio: str = Form(None),
    microcateter: str = Form(None),
    guia: str = Form(None),
    microguia: str = Form(None),
    fd: str = Form(None),
    materiales_usados: str = Form(None),
    complicaciones: str = Form(None),
    notas_adicionales: str = Form(None),
    db: Session = Depends(get_db)
):
    p = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not p:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    p.lugar = lugar
    p.historia_clinica = historia_clinica
    p.paciente_nombre = paciente_nombre
    p.edad = int(edad) if edad and edad.isdigit() else None
    p.procedimiento = procedimiento_txt
    p.diagnostico = diagnostico
    p.localizacion_aneurisma = localizacion_aneurisma
    p.primer_operador = primer_operador
    p.segundo_operador = segundo_operador
    p.fellow = fellow
    p.presentacion_clinica = presentacion_clinica
    p.vaina = vaina
    p.cateter = cateter
    p.cateter_intermedio = cateter_intermedio
    p.microcateter = microcateter
    p.guia = guia
    p.microguia = microguia
    p.fd = fd
    p.materiales_usados = materiales_usados
    p.complicaciones = complicaciones
    p.notas_adicionales = notas_adicionales

    db.commit()

    return RedirectResponse(
        url=f"/procedimientos/{procedimiento_id}",
        status_code=303
    )


@router.post("/procedimientos/{procedimiento_id}/subir-archivo")
async def subir_archivo_procedimiento(
    procedimiento_id: int,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    p = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not p:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    carpeta = Path(DATA_PATH) / "web" / str(procedimiento_id)
    carpeta.mkdir(parents=True, exist_ok=True)

    extension = Path(archivo.filename).suffix or ".bin"
    nombre = f"{uuid.uuid4().hex}{extension}"
    ruta = carpeta / nombre

    with open(ruta, "wb") as buffer:
        shutil.copyfileobj(archivo.file, buffer)

    tipo = "archivo"
    content_type = archivo.content_type or ""

    if content_type.startswith("image/"):
        tipo = "foto"
    elif content_type.startswith("video/"):
        tipo = "video"
    elif "dicom" in content_type.lower() or extension.lower() in [".dcm", ".dicom"]:
        tipo = "dicom"
    elif extension.lower() == ".pdf":
        tipo = "pdf"
    elif extension.lower() == ".zip":
        tipo = "zip"

    nuevo = Archivo(
        procedimiento_id=procedimiento_id,
        tipo=tipo,
        origen="web",
        ruta=str(ruta),
        nombre_original=archivo.filename,
        estado="asociado",
    )

    db.add(nuevo)
    db.commit()

    db.refresh(nuevo)

    if tipo == "zip":
        carpeta_zip = carpeta / f"zip_{nuevo.id}"
        carpeta_zip.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(ruta, "r") as zip_ref:
                zip_ref.extractall(carpeta_zip)

            for archivo_extraido in sorted(carpeta_zip.rglob("*")):
                if archivo_extraido.is_file():
                    ext = archivo_extraido.suffix.lower()

                    tipo_extraido = "archivo"
                    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
                        tipo_extraido = "foto"
                    elif ext in [".mp4", ".mov", ".avi", ".mkv"]:
                        tipo_extraido = "video"
                    elif ext in [".dcm", ".dicom"]:
                        tipo_extraido = "dicom"
                    elif ext == ".pdf":
                        tipo_extraido = "pdf"

                    nuevo_extraido = Archivo(
                        procedimiento_id=procedimiento_id,
                        tipo=tipo_extraido,
                        origen="zip",
                        ruta=str(archivo_extraido),
                        nombre_original=archivo_extraido.name,
                        estado="asociado",
                    )

                    db.add(nuevo_extraido)

            db.commit()

        except zipfile.BadZipFile:
            nuevo.estado = "zip_invalido"
            db.commit()



    return RedirectResponse(
        url=f"/procedimientos/{procedimiento_id}",
        status_code=303
    )


@router.get("/archivos/{archivo_id}")
def obtener_archivo(
    archivo_id: int,
    db: Session = Depends(get_db)
):
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()

    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    ruta = Path(archivo.ruta)

    if not ruta.exists():
        raise HTTPException(status_code=404, detail="Archivo físico no encontrado")

    return FileResponse(ruta)
