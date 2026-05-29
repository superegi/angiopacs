from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
import uuid
import os
import zipfile
from services.orthanc_service import subir_dicom_a_orthanc



from database import get_db
from models import Procedimiento, Archivo, ParticipanteProcedimiento, MaterialProcedimiento, EstudioDICOM, SugerenciaIA, RepositorioTag

ORTHANC_PUBLIC_URL = os.getenv("ORTHANC_PUBLIC_URL", "http://localhost:8042")

router = APIRouter()
templates = Jinja2Templates(directory="templates")

DATA_PATH = os.getenv("DATA_PATH", "/app/data")

def asegurar_tag(db: Session, tipo: str, nombre: str | None):
    if not nombre:
        return None

    nombre_limpio = nombre.strip()
    if not nombre_limpio:
        return None

    existente = (
        db.query(RepositorioTag)
        .filter(
            RepositorioTag.tipo == tipo,
            RepositorioTag.nombre == nombre_limpio,
        )
        .first()
    )

    if existente:
        return existente

    tag = RepositorioTag(
        tipo=tipo,
        nombre=nombre_limpio,
        activo=True,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def listar_nombres_tag(db: Session, tipo: str):
    tags = (
        db.query(RepositorioTag)
        .filter(
            RepositorioTag.tipo == tipo,
            RepositorioTag.activo == True,
        )
        .order_by(RepositorioTag.nombre.asc())
        .all()
    )
    return [t.nombre for t in tags]




@router.get("/repositorios")
def ver_repositorios(
    request: Request,
    db: Session = Depends(get_db)
):
    tags = (
        db.query(RepositorioTag)
        .order_by(RepositorioTag.tipo.asc(), RepositorioTag.nombre.asc())
        .all()
    )

    agrupados = {}

    for tag in tags:
        if tag.tipo not in agrupados:
            agrupados[tag.tipo] = []
        agrupados[tag.tipo].append(tag)

    return templates.TemplateResponse(
        request=request,
        name="repositorios.html",
        context={
            "agrupados": agrupados,
        }
    )



@router.post("/repositorios/{tag_id}/renombrar")
def renombrar_tag_repositorio(
    tag_id: int,
    nombre: str = Form(...),
    db: Session = Depends(get_db)
):
    tag = db.query(RepositorioTag).filter(RepositorioTag.id == tag_id).first()

    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")

    nombre_limpio = nombre.strip()

    if nombre_limpio:
        tag.nombre = nombre_limpio
        db.commit()

    return RedirectResponse(
        url="/repositorios",
        status_code=303
    )


@router.post("/repositorios/{tag_id}/desactivar")
def desactivar_tag_repositorio(
    tag_id: int,
    db: Session = Depends(get_db)
):
    tag = db.query(RepositorioTag).filter(RepositorioTag.id == tag_id).first()

    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")

    tag.activo = False
    db.commit()

    return RedirectResponse(
        url="/repositorios",
        status_code=303
    )


@router.post("/repositorios/{tag_id}/activar")
def activar_tag_repositorio(
    tag_id: int,
    db: Session = Depends(get_db)
):
    tag = db.query(RepositorioTag).filter(RepositorioTag.id == tag_id).first()

    if not tag:
        raise HTTPException(status_code=404, detail="Tag no encontrado")

    tag.activo = True
    db.commit()

    return RedirectResponse(
        url="/repositorios",
        status_code=303
    )



@router.post("/repositorios/{tag_id}/fusionar")
def fusionar_tag_repositorio(
    tag_id: int,
    destino_id: int = Form(...),
    db: Session = Depends(get_db)
):
    origen = db.query(RepositorioTag).filter(RepositorioTag.id == tag_id).first()
    destino = db.query(RepositorioTag).filter(RepositorioTag.id == destino_id).first()

    if not origen or not destino:
        raise HTTPException(status_code=404, detail="Tag no encontrado")

    if origen.id == destino.id:
        return RedirectResponse(url="/repositorios", status_code=303)

    if origen.tipo != destino.tipo:
        raise HTTPException(status_code=400, detail="Solo se pueden fusionar tags del mismo tipo")

    nombre_origen = origen.nombre
    nombre_destino = destino.nombre

    if origen.tipo == "persona":
        db.query(ParticipanteProcedimiento).filter(
            ParticipanteProcedimiento.nombre == nombre_origen
        ).update({"nombre": nombre_destino})

    elif origen.tipo == "rol_procedimiento":
        db.query(ParticipanteProcedimiento).filter(
            ParticipanteProcedimiento.rol == nombre_origen
        ).update({"rol": nombre_destino})

    elif origen.tipo == "material":
        db.query(MaterialProcedimiento).filter(
            MaterialProcedimiento.nombre == nombre_origen
        ).update({"nombre": nombre_destino})

    elif origen.tipo == "tipo_material":
        db.query(MaterialProcedimiento).filter(
            MaterialProcedimiento.tipo_material == nombre_origen
        ).update({"tipo_material": nombre_destino})

    elif origen.tipo == "procedimiento":
        db.query(Procedimiento).filter(
            Procedimiento.procedimiento == nombre_origen
        ).update({"procedimiento": nombre_destino})

    elif origen.tipo == "institucion":
        db.query(Procedimiento).filter(
            Procedimiento.institucion == nombre_origen
        ).update({"institucion": nombre_destino})

    origen.activo = False
    db.commit()

    return RedirectResponse(
        url="/repositorios",
        status_code=303
    )


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

    otros_archivos = []
    dicom_grupos = {}

    for archivo in archivos:
        if archivo.tipo == "dicom":
            clave = archivo.orthanc_study_id or archivo.study_instance_uid or "sin_estudio"

            if clave not in dicom_grupos:
                dicom_grupos[clave] = {
                    "clave": clave,
                    "orthanc_study_id": archivo.orthanc_study_id,
                    "study_instance_uid": archivo.study_instance_uid,
                    "archivos": [],
                }

            dicom_grupos[clave]["archivos"].append(archivo)
        else:
            otros_archivos.append(archivo)

    dicom_grupos = list(dicom_grupos.values())

    participantes = (
        db.query(ParticipanteProcedimiento)
        .filter(ParticipanteProcedimiento.procedimiento_id == procedimiento_id)
        .order_by(ParticipanteProcedimiento.id.asc())
        .all()
    )

    materiales = (
        db.query(MaterialProcedimiento)
        .filter(MaterialProcedimiento.procedimiento_id == procedimiento_id)
        .order_by(MaterialProcedimiento.id.asc())
        .all()
    )

    estudios_dicom = (
        db.query(EstudioDICOM)
        .filter(EstudioDICOM.procedimiento_id == procedimiento_id)
        .order_by(EstudioDICOM.id.asc())
        .all()
    )

    sugerencias_ia = (
        db.query(SugerenciaIA)
        .filter(
            SugerenciaIA.procedimiento_id == procedimiento_id,
            SugerenciaIA.estado == "pendiente"
        )
        .order_by(SugerenciaIA.id.desc())
        .all()
    )

    sugerencias_personas = listar_nombres_tag(db, "persona")
    sugerencias_roles = listar_nombres_tag(db, "rol_procedimiento")
    sugerencias_materiales = listar_nombres_tag(db, "material")
    sugerencias_tipos_material = listar_nombres_tag(db, "tipo_material")

    return templates.TemplateResponse(
        request=request,
        name="procedimiento_detalle.html",
        context={
            "procedimiento": procedimiento,
            "archivos": otros_archivos,
            "dicom_grupos": dicom_grupos,
            "estudios_dicom": estudios_dicom,
            "participantes": participantes,
            "materiales": materiales,
            "sugerencias_ia": sugerencias_ia,
            "sugerencias_personas": sugerencias_personas,
            "sugerencias_roles": sugerencias_roles,
            "sugerencias_materiales": sugerencias_materiales,
            "sugerencias_tipos_material": sugerencias_tipos_material,
            "orthanc_public_url": ORTHANC_PUBLIC_URL,

        }
    )


@router.post("/procedimientos/{procedimiento_id}/participantes/agregar")
async def agregar_participante_procedimiento(
    procedimiento_id: int,
    nombre: str = Form(...),
    rol: str = Form(...),
    notas: str = Form(None),
    db: Session = Depends(get_db)
):
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    participante = ParticipanteProcedimiento(
        procedimiento_id=procedimiento_id,
        nombre=nombre,
        rol=rol,
        notas=notas,
    )

    db.add(participante)
    db.commit()

    asegurar_tag(db, "persona", nombre)
    asegurar_tag(db, "rol_procedimiento", rol)

    return RedirectResponse(
        url=f"/procedimientos/{procedimiento_id}",
        status_code=303
    )


@router.post("/procedimientos/{procedimiento_id}/materiales/agregar")
async def agregar_material_procedimiento(
    procedimiento_id: int,
    nombre: str = Form(...),
    tipo_material: str = Form(None),
    cantidad: str = Form("1"),
    notas: str = Form(None),
    db: Session = Depends(get_db)
):
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    cantidad_int = int(cantidad) if cantidad and cantidad.isdigit() else 1

    material = MaterialProcedimiento(
        procedimiento_id=procedimiento_id,
        nombre=nombre,
        tipo_material=tipo_material,
        cantidad=cantidad_int,
        notas=notas,
    )

    db.add(material)
    db.commit()

    asegurar_tag(db, "material", nombre)
    asegurar_tag(db, "tipo_material", tipo_material)

    return RedirectResponse(
        url=f"/procedimientos/{procedimiento_id}",
        status_code=303
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

    if tipo == "dicom":
        try:
            info_orthanc = subir_dicom_a_orthanc(str(ruta))
            nuevo.orthanc_instance_id = info_orthanc.get("orthanc_instance_id")
            nuevo.orthanc_study_id = info_orthanc.get("orthanc_study_id")
            nuevo.study_instance_uid = info_orthanc.get("study_instance_uid")

            if nuevo.orthanc_study_id:
                p.dicom_orthanc_id = nuevo.orthanc_study_id
            if nuevo.study_instance_uid:
                p.study_instance_uid = nuevo.study_instance_uid

        except Exception as e:
            nuevo.estado = f"error_orthanc: {str(e)[:120]}"

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

                    if tipo_extraido == "dicom":
                        try:
                            info_orthanc = subir_dicom_a_orthanc(str(archivo_extraido))

                            nuevo_extraido.orthanc_instance_id = info_orthanc.get("orthanc_instance_id")
                            nuevo_extraido.orthanc_study_id = info_orthanc.get("orthanc_study_id")
                            nuevo_extraido.study_instance_uid = info_orthanc.get("study_instance_uid")

                            if nuevo_extraido.orthanc_study_id:
                                p.dicom_orthanc_id = nuevo_extraido.orthanc_study_id

                            if nuevo_extraido.study_instance_uid:
                                p.study_instance_uid = nuevo_extraido.study_instance_uid

                        except Exception as e:
                            nuevo_extraido.estado = f"error_orthanc: {str(e)[:120]}"

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
