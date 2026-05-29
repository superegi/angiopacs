from fastapi import APIRouter, Depends, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import shutil
import uuid
import os
import zipfile
import json
from datetime import datetime
from services.orthanc_service import subir_dicom_a_orthanc



from database import get_db
from models import Procedimiento, Archivo, ParticipanteProcedimiento, MaterialProcedimiento, EstudioDICOM, SugerenciaIA, RepositorioTag

ORTHANC_PUBLIC_URL = os.getenv("ORTHANC_PUBLIC_URL", "http://localhost:8042")

router = APIRouter()
templates = Jinja2Templates(directory="templates")

DATA_PATH = os.getenv("DATA_PATH", "/app/data")

def parse_date_or_none(value: str | None):
    if not value:
        return None

    value = value.strip()
    if not value:
        return None

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def calcular_edad(fecha_nacimiento, fecha_referencia=None):
    if not fecha_nacimiento:
        return None

    if fecha_referencia is None:
        fecha_referencia = datetime.utcnow().date()

    edad = fecha_referencia.year - fecha_nacimiento.year

    if (fecha_referencia.month, fecha_referencia.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
        edad -= 1

    return edad



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



def calcular_edad(fecha_nacimiento, fecha_referencia=None):
    if not fecha_nacimiento:
        return None

    if fecha_referencia is None:
        fecha_referencia = datetime.utcnow().date()

    edad = fecha_referencia.year - fecha_nacimiento.year

    if (fecha_referencia.month, fecha_referencia.day) < (fecha_nacimiento.month, fecha_nacimiento.day):
        edad -= 1

    return edad


def registrar_estudio_dicom_desde_archivo(db: Session, archivo: Archivo, procedimiento_id: int | None = None, cache_uids: set | None = None):
    if not archivo.study_instance_uid:
        return None

    uid = archivo.study_instance_uid

    if cache_uids is not None and uid in cache_uids:
        return None

    estudio = (
        db.query(EstudioDICOM)
        .filter(EstudioDICOM.study_instance_uid == uid)
        .first()
    )

    if estudio:
        if procedimiento_id is not None:
            estudio.procedimiento_id = procedimiento_id
            estudio.estado = "asociado"

        if archivo.orthanc_study_id:
            estudio.orthanc_study_id = archivo.orthanc_study_id

        estudio.actualizado_en = datetime.utcnow()

        if cache_uids is not None:
            cache_uids.add(uid)

        return estudio

    estudio = EstudioDICOM(
        procedimiento_id=procedimiento_id,
        study_instance_uid=uid,
        orthanc_study_id=archivo.orthanc_study_id,
        patient_name=None,
        patient_id=None,
        modality="XA",
        rol_en_caso="dicom_procedimiento",
        estado="asociado" if procedimiento_id else "huerfano",
    )

    db.add(estudio)

    if cache_uids is not None:
        cache_uids.add(uid)

    return estudio


@router.get("/auditoria")
def ver_auditoria(
    request: Request,
    db: Session = Depends(get_db)
):
    estudios_huerfanos = (
        db.query(EstudioDICOM)
        .filter(EstudioDICOM.procedimiento_id.is_(None))
        .order_by(EstudioDICOM.id.desc())
        .all()
    )

    archivos_huerfanos = (
        db.query(Archivo)
        .filter(Archivo.procedimiento_id.is_(None))
        .order_by(Archivo.id.desc())
        .all()
    )

    procedimientos = (
        db.query(Procedimiento)
        .order_by(Procedimiento.id.desc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="auditoria.html",
        context={
            "estudios_huerfanos": estudios_huerfanos,
            "archivos_huerfanos": archivos_huerfanos,
            "procedimientos": procedimientos,
        }
    )


@router.post("/auditoria/dicom/{estudio_id}/asociar")
def asociar_dicom_desde_auditoria(
    estudio_id: int,
    procedimiento_id: int = Form(...),
    rol_en_caso: str = Form("angiografia_procedimiento"),
    db: Session = Depends(get_db)
):
    estudio = db.query(EstudioDICOM).filter(EstudioDICOM.id == estudio_id).first()
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not estudio:
        raise HTTPException(status_code=404, detail="Estudio DICOM no encontrado")

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    estudio.procedimiento_id = procedimiento_id
    estudio.rol_en_caso = rol_en_caso
    estudio.estado = "asociado"

    if estudio.orthanc_study_id:
        procedimiento.dicom_orthanc_id = estudio.orthanc_study_id

    if estudio.study_instance_uid:
        procedimiento.study_instance_uid = estudio.study_instance_uid

    db.commit()

    return RedirectResponse(
        url="/auditoria",
        status_code=303
    )


@router.post("/auditoria/archivo/{archivo_id}/asociar")
def asociar_archivo_desde_auditoria(
    archivo_id: int,
    procedimiento_id: int = Form(...),
    db: Session = Depends(get_db)
):
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    archivo.procedimiento_id = procedimiento_id
    archivo.estado = "asociado"
    db.commit()

    return RedirectResponse(
        url="/auditoria",
        status_code=303
    )


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



@router.get("/nuevo-caso")
def nuevo_caso_get(
    request: Request,
    db: Session = Depends(get_db)
):
    sugerencias_instituciones = listar_nombres_tag(db, "institucion") if "listar_nombres_tag" in globals() else []
    sugerencias_procedimientos = listar_nombres_tag(db, "procedimiento") if "listar_nombres_tag" in globals() else []

    return templates.TemplateResponse(
        request=request,
        name="nuevo_caso.html",
        context={
            "sugerencias_instituciones": sugerencias_instituciones,
            "sugerencias_procedimientos": sugerencias_procedimientos,
        }
    )


@router.post("/nuevo-caso")
def nuevo_caso_post(
    paciente_nombre: str = Form(None),
    paciente_apellido: str = Form(None),
    paciente_sexo: str = Form(None),
    paciente_fecha_nacimiento: str = Form(None),
    paciente_id: str = Form(None),
    edad: str = Form(None),
    historia_clinica: str = Form(None),
    institucion: str = Form(None),
    fecha: str = Form(None),
    procedimiento_txt: str = Form(None),
    diagnostico: str = Form(None),
    presentacion_clinica: str = Form(None),
    db: Session = Depends(get_db)
):
    edad_int = int(edad) if edad and edad.isdigit() else None

    procedimiento = Procedimiento(
        paciente_nombre=paciente_nombre.strip() if paciente_nombre else None,
        paciente_apellido=paciente_apellido.strip() if paciente_apellido else None,
        paciente_sexo=paciente_sexo.strip() if paciente_sexo else None,
        paciente_fecha_nacimiento=parse_date_or_none(paciente_fecha_nacimiento),
        paciente_id=paciente_id.strip() if paciente_id else None,
        edad=edad_int,
        historia_clinica=historia_clinica.strip() if historia_clinica else None,
        institucion=institucion.strip() if institucion else None,
        fecha=parse_date_or_none(fecha),
        procedimiento=procedimiento_txt.strip() if procedimiento_txt else None,
        diagnostico=diagnostico.strip() if diagnostico else None,
        presentacion_clinica=presentacion_clinica.strip() if presentacion_clinica else None,
    )

    db.add(procedimiento)
    db.commit()
    db.refresh(procedimiento)

    if "asegurar_tag" in globals():
        asegurar_tag(db, "institucion", institucion)
        asegurar_tag(db, "procedimiento", procedimiento_txt)

    return RedirectResponse(
        url=f"/procedimientos/{procedimiento.id}",
        status_code=303
    )



def asegurar_tag(db: Session, tipo: str, nombre: str | None):
    if not nombre:
        return None

    nombre_limpio = str(nombre).strip()
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
    sugerencias_instituciones = listar_nombres_tag(db, "institucion")
    sugerencias_procedimientos = listar_nombres_tag(db, "procedimiento")

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
            "sugerencias_instituciones": sugerencias_instituciones,
            "sugerencias_procedimientos": sugerencias_procedimientos,
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



@router.post("/procedimientos/{procedimiento_id}/participantes/{participante_id}/eliminar")
def eliminar_participante_procedimiento(
    procedimiento_id: int,
    participante_id: int,
    db: Session = Depends(get_db)
):
    participante = (
        db.query(ParticipanteProcedimiento)
        .filter(
            ParticipanteProcedimiento.id == participante_id,
            ParticipanteProcedimiento.procedimiento_id == procedimiento_id,
        )
        .first()
    )

    if not participante:
        raise HTTPException(status_code=404, detail="Participante no encontrado")

    db.delete(participante)
    db.commit()

    return RedirectResponse(
        url=f"/procedimientos/{procedimiento_id}",
        status_code=303
    )


@router.post("/procedimientos/{procedimiento_id}/materiales/{material_id}/eliminar")
def eliminar_material_procedimiento(
    procedimiento_id: int,
    material_id: int,
    db: Session = Depends(get_db)
):
    material = (
        db.query(MaterialProcedimiento)
        .filter(
            MaterialProcedimiento.id == material_id,
            MaterialProcedimiento.procedimiento_id == procedimiento_id,
        )
        .first()
    )

    if not material:
        raise HTTPException(status_code=404, detail="Material no encontrado")

    db.delete(material)
    db.commit()

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
    paciente_apellido: str = Form(None),
    paciente_sexo: str = Form(None),
    paciente_fecha_nacimiento: str = Form(None),
    paciente_id: str = Form(None),
    fecha: str = Form(None),
    proxima_visita_agendada: str = Form(None),
    institucion: str = Form(None),
    edad: str = Form(None),
    procedimiento_txt: str = Form(None),
    diagnostico: str = Form(None),
    presentacion_clinica: str = Form(None),
    indicaciones: str = Form(None),
    complicaciones_si_no: str = Form(None),
    complicaciones: str = Form(None),
    notas_adicionales: str = Form(None),
    localizacion_aneurisma: str = Form(None),
    primer_operador: str = Form(None),
    segundo_operador: str = Form(None),
    fellow: str = Form(None),
    vaina: str = Form(None),
    cateter: str = Form(None),
    cateter_intermedio: str = Form(None),
    microcateter: str = Form(None),
    guia: str = Form(None),
    microguia: str = Form(None),
    fd: str = Form(None),
    materiales_usados: str = Form(None),
    db: Session = Depends(get_db)
):
    p = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not p:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    p.lugar = lugar
    p.historia_clinica = historia_clinica
    p.paciente_nombre = paciente_nombre
    p.paciente_apellido = paciente_apellido
    p.paciente_sexo = paciente_sexo
    p.paciente_fecha_nacimiento = parse_date_or_none(paciente_fecha_nacimiento)
    p.paciente_id = paciente_id
    p.fecha = parse_date_or_none(fecha)
    p.proxima_visita_agendada = parse_date_or_none(proxima_visita_agendada)
    p.institucion = institucion.strip() if institucion else None

    if "asegurar_tag" in globals():
        asegurar_tag(db, "institucion", institucion)

    edad_calculada = calcular_edad(p.paciente_fecha_nacimiento, p.fecha)
    p.edad = edad_calculada if edad_calculada is not None else (int(edad) if edad and edad.isdigit() else None)

    p.procedimiento = procedimiento_txt
    p.diagnostico = diagnostico
    p.indicaciones = indicaciones
    p.complicaciones_si_no = complicaciones_si_no
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
    categoria: str = Form(None),
    caption: str = Form(None),
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
        categoria=categoria.strip() if categoria else None,
        caption=caption.strip() if caption else None,
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

            registrar_estudio_dicom_desde_archivo(db, nuevo, procedimiento_id, set())

        except Exception as e:
            nuevo.estado = f"error_orthanc: {str(e)[:120]}"

    db.add(nuevo)
    db.commit()

    db.refresh(nuevo)

    if tipo == "zip":
        dicom_study_uids_registrados = set()
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
                    categoria=categoria.strip() if categoria else None,
                    caption=caption.strip() if caption else None,
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

                            registrar_estudio_dicom_desde_archivo(db, nuevo_extraido, procedimiento_id, dicom_study_uids_registrados)

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




@router.post("/archivos/{archivo_id}/metadata")
def actualizar_metadata_archivo(
    archivo_id: int,
    categoria: str = Form(None),
    caption: str = Form(None),
    db: Session = Depends(get_db)
):
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()

    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    archivo.categoria = categoria.strip() if categoria else None
    archivo.caption = caption.strip() if caption else None

    db.commit()

    if archivo.procedimiento_id:
        return RedirectResponse(
            url=f"/procedimientos/{archivo.procedimiento_id}",
            status_code=303
        )

    return RedirectResponse(
        url="/auditoria",
        status_code=303
    )


@router.post("/archivos/{archivo_id}/eliminar")
def eliminar_archivo_procedimiento(
    archivo_id: int,
    db: Session = Depends(get_db)
):
    archivo = db.query(Archivo).filter(Archivo.id == archivo_id).first()

    if not archivo:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    procedimiento_id = archivo.procedimiento_id

    try:
        ruta = Path(archivo.ruta)
        if ruta.exists() and ruta.is_file():
            ruta.unlink()
    except Exception:
        pass

    db.delete(archivo)
    db.commit()

    if procedimiento_id:
        return RedirectResponse(
            url=f"/procedimientos/{procedimiento_id}",
            status_code=303
        )

    return RedirectResponse(
        url="/auditoria",
        status_code=303
    )


@router.get("/procedimientos/{procedimiento_id}/exportar")
def exportar_procedimiento_zip(
    procedimiento_id: int,
    db: Session = Depends(get_db)
):
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    archivos = (
        db.query(Archivo)
        .filter(Archivo.procedimiento_id == procedimiento_id)
        .order_by(Archivo.id.asc())
        .all()
    )

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

    # Politica de exportacion:
    # - El ZIP principal del caso NO duplica ZIP originales subidos.
    # - El ZIP principal del caso NO incluye DICOM pesados.
    # - DICOM queda referenciado por StudyInstanceUID / Orthanc ID.
    # - En una etapa posterior se generara un ZIP DICOM separado por estudio.
    archivos_exportables = [
        a for a in archivos
        if (a.tipo or "").lower() not in ["zip", "dicom"]
    ]

    archivos_excluidos = [
        a for a in archivos
        if (a.tipo or "").lower() in ["zip", "dicom"]
    ]

    export_dir = Path(DATA_PATH) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_path = export_dir / f"caso_{procedimiento_id}_{timestamp}.zip"

    case_data = {
        "schema_version": "1.0.0",
        "app_version": "0.1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "case": {
            "id": procedimiento.id,
            "paciente_nombre": procedimiento.paciente_nombre,
            "paciente_apellido": getattr(procedimiento, "paciente_apellido", None),
            "paciente_sexo": getattr(procedimiento, "paciente_sexo", None),
            "paciente_fecha_nacimiento": str(procedimiento.paciente_fecha_nacimiento) if getattr(procedimiento, "paciente_fecha_nacimiento", None) else None,
            "paciente_id": getattr(procedimiento, "paciente_id", None),
            "edad": procedimiento.edad,
            "historia_clinica": procedimiento.historia_clinica,
            "lugar": procedimiento.lugar,
            "institucion": getattr(procedimiento, "institucion", None),
            "fecha": str(procedimiento.fecha) if procedimiento.fecha else None,
            "procedimiento": procedimiento.procedimiento,
            "diagnostico": procedimiento.diagnostico,
            "presentacion_clinica": procedimiento.presentacion_clinica,
            "informe_procedimiento": getattr(procedimiento, "informe_procedimiento", None),
            "complicaciones": procedimiento.complicaciones,
            "notas_adicionales": procedimiento.notas_adicionales,
            "extra_fields": {},
        },
        "participants": [
            {
                "id": p.id,
                "nombre": p.nombre,
                "rol": p.rol,
                "notas": p.notas,
            }
            for p in participantes
        ],
        "materials": [
            {
                "id": m.id,
                "nombre": m.nombre,
                "tipo_material": m.tipo_material,
                "cantidad": m.cantidad,
                "notas": m.notas,
            }
            for m in materiales
        ],
        "dicom_studies": [
            {
                "id": e.id,
                "study_instance_uid": e.study_instance_uid,
                "orthanc_study_id": e.orthanc_study_id,
                "patient_name": e.patient_name,
                "patient_id": e.patient_id,
                "accession_number": e.accession_number,
                "study_date": e.study_date,
                "modality": e.modality,
                "rol_en_caso": e.rol_en_caso,
                "estado": e.estado,
            }
            for e in estudios_dicom
        ],
        "files": [
            {
                "id": a.id,
                "tipo": a.tipo,
                "categoria": getattr(a, "categoria", None),
                "caption": getattr(a, "caption", None),
                "origen": a.origen,
                "nombre_original": a.nombre_original,
                "ruta_relativa_export": f"files/{a.id}_{a.nombre_original or Path(a.ruta).name}",
                "estado": a.estado,
            }
            for a in archivos_exportables
        ],
        "excluded_files": [
            {
                "id": a.id,
                "tipo": a.tipo,
                "origen": a.origen,
                "nombre_original": a.nombre_original,
                "motivo": "excluido_para_evitar_duplicacion_o_peso_dicom",
                "estado": a.estado,
                "study_instance_uid": getattr(a, "study_instance_uid", None),
                "orthanc_study_id": getattr(a, "orthanc_study_id", None),
            }
            for a in archivos_excluidos
        ],
        "extra_fields": {},
    }

    md_lines = []
    md_lines.append(f"# Caso {procedimiento.id}")
    md_lines.append("")
    md_lines.append(f"- Paciente: {procedimiento.paciente_nombre or ''} {getattr(procedimiento, 'paciente_apellido', '') or ''}")
    md_lines.append(f"- ID paciente: {getattr(procedimiento, 'paciente_id', '') or ''}")
    md_lines.append(f"- Historia clinica: {procedimiento.historia_clinica or ''}")
    md_lines.append(f"- Fecha: {procedimiento.fecha or ''}")
    md_lines.append(f"- Institucion: {getattr(procedimiento, 'institucion', '') or ''}")
    md_lines.append(f"- Procedimiento: {procedimiento.procedimiento or ''}")
    md_lines.append("")
    md_lines.append("## Diagnostico")
    md_lines.append(procedimiento.diagnostico or "")
    md_lines.append("")
    md_lines.append("## Presentacion clinica")
    md_lines.append(procedimiento.presentacion_clinica or "")
    md_lines.append("")
    md_lines.append("## Participantes")
    for p in participantes:
        md_lines.append(f"- {p.nombre} ({p.rol}) {p.notas or ''}")
    md_lines.append("")
    md_lines.append("## Materiales")
    for m in materiales:
        md_lines.append(f"- {m.nombre} | {m.tipo_material or ''} | cantidad: {m.cantidad or 1} | {m.notas or ''}")
    md_lines.append("")
    md_lines.append("## Estudios DICOM")
    for e in estudios_dicom:
        md_lines.append(f"- StudyInstanceUID: {e.study_instance_uid} | Orthanc: {e.orthanc_study_id or ''} | Rol: {e.rol_en_caso or ''}")
    md_lines.append("")
    md_lines.append("## Complicaciones")
    md_lines.append(procedimiento.complicaciones or "")
    md_lines.append("")
    md_lines.append("## Notas adicionales")
    md_lines.append(procedimiento.notas_adicionales or "")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("case.json", json.dumps(case_data, ensure_ascii=False, indent=2))
        zipf.writestr("case.md", "\n".join(md_lines))

        manifest = {
            "schema_version": "1.0.0",
            "app_version": "0.1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "case_id": procedimiento.id,
            "contains_dicom_files": False,
            "dicom_policy": "DICOM is referenced by StudyInstanceUID/Orthanc ID. Full DICOM files are not duplicated in this export.",
            "zip_policy": "Original uploaded ZIP files are not re-exported when extracted files exist, to avoid duplicated payloads.",
            "exported_files_count": len(archivos_exportables),
            "excluded_files_count": len(archivos_excluidos),
        }
        zipf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        for archivo in archivos_exportables:
            try:
                src = Path(archivo.ruta)
                if src.exists() and src.is_file():
                    arcname = f"files/{archivo.id}_{archivo.nombre_original or src.name}"
                    zipf.write(src, arcname)
            except Exception:
                continue

    return FileResponse(
        path=zip_path,
        filename=zip_path.name,
        media_type="application/zip"
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
