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
import unicodedata
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
    paciente_mail: str = Form(None),
    paciente_telefono: str = Form(None),
    estado_caso: str = Form("abierto"),
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
        paciente_mail=paciente_mail.strip() if paciente_mail else None,
        paciente_telefono=paciente_telefono.strip() if paciente_telefono else None,
        estado_caso=estado_caso.strip() if estado_caso else "abierto",
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
    paciente_mail: str = Form(None),
    paciente_telefono: str = Form(None),
    estado_caso: str = Form("abierto"),
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
    p.paciente_mail = paciente_mail.strip() if paciente_mail else None
    p.paciente_telefono = paciente_telefono.strip() if paciente_telefono else None
    p.estado_caso = estado_caso.strip() if estado_caso else "abierto"
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


@router.post("/procedimientos/{procedimiento_id}/subir-archivo-legacy")
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
            nuevo.estado="error_orthanc"

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
                            nuevo_extraido.estado="error_orthanc"

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
    zip_path = _angio_041_zip_path(export_dir, procedimiento)

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
            "paciente_mail": getattr(procedimiento, "paciente_mail", None),
            "paciente_telefono": getattr(procedimiento, "paciente_telefono", None),
            "estado_caso": getattr(procedimiento, "estado_caso", None),
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
    md_lines.append(f"- Mail paciente: {getattr(procedimiento, 'paciente_mail', '') or ''}")
    md_lines.append(f"- Teléfono paciente: {getattr(procedimiento, 'paciente_telefono', '') or ''}")
    md_lines.append(f"- Estado caso: {getattr(procedimiento, 'estado_caso', '') or ''}")
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


# ============================================================
# ANGIO-024/025: upload robusto ZIP/DICOM + reintento Orthanc
# ============================================================

def _angio_nombre_seguro(nombre: str | None) -> str:
    nombre = Path(nombre or "archivo").name
    nombre = nombre.replace("/", "_").replace("\\", "_").strip()
    return nombre or "archivo"


def _angio_tipo_por_nombre(nombre: str | None) -> str:
    ext = Path(nombre or "").suffix.lower()

    if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"]:
        return "foto"
    if ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
        return "video"
    if ext == ".zip":
        return "zip"
    if ext in [".dcm", ".dicom", ".ima"]:
        return "dicom"
    if ext == ".pdf":
        return "pdf"

    return "archivo"


def _angio_guardar_bytes(procedimiento_id: int, nombre_original: str, data: bytes, subcarpeta: str = "web") -> Path:
    carpeta = Path(DATA_PATH) / subcarpeta / str(procedimiento_id)
    carpeta.mkdir(parents=True, exist_ok=True)

    destino = carpeta / f"{uuid.uuid4().hex}_{_angio_nombre_seguro(nombre_original)}"

    with open(destino, "wb") as f:
        f.write(data)

    return destino


def _angio_crear_archivo(
    db: Session,
    procedimiento_id: int,
    ruta: Path,
    nombre_original: str,
    origen: str,
    categoria: str | None = None,
    caption: str | None = None,
):
    archivo = Archivo(
        procedimiento_id=procedimiento_id,
        tipo=_angio_tipo_por_nombre(nombre_original),
        categoria=categoria,
        caption=caption,
        origen=origen,
        ruta=str(ruta),
        nombre_original=nombre_original,
        estado="asociado",
    )

    db.add(archivo)
    db.flush()
    return archivo


def _angio_intentar_orthanc(db: Session, archivo: Archivo, procedimiento_id: int):
    """
    Intenta subir un archivo a Orthanc.
    Si falla, NO revienta el flujo completo.
    Guarda error largo en razon_match, no en estado.
    """
    try:
        resultado = subir_dicom_a_orthanc(archivo.ruta)

        archivo.tipo = "dicom"
        archivo.estado = "asociado"
        archivo.razon_match = None
        archivo.orthanc_instance_id = resultado.get("orthanc_instance_id")
        archivo.orthanc_study_id = resultado.get("orthanc_study_id")
        archivo.study_instance_uid = resultado.get("study_instance_uid")

        estudio = registrar_estudio_dicom_desde_archivo(
            db=db,
            archivo=archivo,
            procedimiento_id=procedimiento_id,
        )

        return estudio

    except Exception as e:
        archivo.tipo = "dicom"
        archivo.estado = "error_orthanc"
        archivo.razon_match = str(e)[:1500]
        return None


@router.post("/procedimientos/{procedimiento_id}/archivos/subir")
@router.post("/procedimientos/{procedimiento_id}/subir-archivo")
async def subir_archivo_procedimiento_robusto(
    procedimiento_id: int,
    request: Request,
    archivos: list[UploadFile] = File(None),
    archivo: UploadFile = File(None),
    categoria: str = Form(None),
    caption: str = Form(None),
    db: Session = Depends(get_db),
):
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    recibidos = []

    if archivos:
        recibidos.extend([a for a in archivos if a is not None])

    if archivo is not None:
        recibidos.append(archivo)

    if not recibidos:
        return RedirectResponse(url=f"/procedimientos/{procedimiento_id}", status_code=303)

    for upload in recibidos:
        nombre = _angio_nombre_seguro(upload.filename)
        data = await upload.read()

        if not data:
            continue

        tipo = _angio_tipo_por_nombre(nombre)
        ruta = _angio_guardar_bytes(procedimiento_id, nombre, data, subcarpeta="web")

        archivo_db = _angio_crear_archivo(
            db=db,
            procedimiento_id=procedimiento_id,
            ruta=ruta,
            nombre_original=nombre,
            origen="web",
            categoria=categoria,
            caption=caption,
        )

        # DICOM suelto
        if tipo == "dicom":
            _angio_intentar_orthanc(db, archivo_db, procedimiento_id)

        # ZIP: guardar original + extraer contenido
        if tipo == "zip":
            archivo_db.estado = "zip_original"

            carpeta_extraida = ruta.parent / f"zip_{archivo_db.id}"
            carpeta_extraida.mkdir(parents=True, exist_ok=True)

            try:
                with zipfile.ZipFile(ruta, "r") as z:
                    for member in z.infolist():
                        if member.is_dir():
                            continue

                        member_name = _angio_nombre_seguro(member.filename)

                        if not member_name or member_name.startswith("."):
                            continue

                        destino = carpeta_extraida / member_name

                        with z.open(member) as src, open(destino, "wb") as dst:
                            shutil.copyfileobj(src, dst)

                        extraido_db = _angio_crear_archivo(
                            db=db,
                            procedimiento_id=procedimiento_id,
                            ruta=destino,
                            nombre_original=member_name,
                            origen="zip",
                            categoria=categoria,
                            caption=caption,
                        )

                        if _angio_tipo_por_nombre(member_name) == "dicom":
                            _angio_intentar_orthanc(db, extraido_db, procedimiento_id)

            except zipfile.BadZipFile:
                archivo_db.estado = "error_zip"
                archivo_db.razon_match = "ZIP inválido o corrupto."

        db.commit()

    procedimiento.actualizado_en = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/procedimientos/{procedimiento_id}", status_code=303)


@router.post("/procedimientos/{procedimiento_id}/dicom/reintentar-orthanc-legacy")
def reintentar_orthanc_procedimiento(
    procedimiento_id: int,
    db: Session = Depends(get_db),
):
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    archivos_dicom = (
        db.query(Archivo)
        .filter(
            Archivo.procedimiento_id == procedimiento_id,
            Archivo.tipo == "dicom",
        )
        .order_by(Archivo.id.asc())
        .all()
    )

    for archivo_db in archivos_dicom:
        if archivo_db.study_instance_uid and archivo_db.orthanc_study_id:
            continue

        ruta = Path(archivo_db.ruta)

        if not ruta.exists():
            archivo_db.estado = "error_archivo_no_existe"
            archivo_db.razon_match = "El archivo no existe en disco."
            continue

        _angio_intentar_orthanc(db, archivo_db, procedimiento_id)
        db.commit()

    procedimiento.actualizado_en = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/procedimientos/{procedimiento_id}", status_code=303)


# ============================================================
# ANGIO-026/028: reintento Orthanc ampliado y diagnóstico visible
# ============================================================

def _angio_026_es_dicom_archivo(archivo: Archivo) -> bool:
    nombre = f"{archivo.nombre_original or ''} {archivo.ruta or ''}".lower()

    if archivo.tipo == "dicom":
        return True

    if ".dcm" in nombre or ".ima" in nombre or ".dicom" in nombre:
        return True

    return False


def _angio_026_intentar_orthanc(db: Session, archivo: Archivo, procedimiento_id: int):
    try:
        resultado = subir_dicom_a_orthanc(archivo.ruta)

        archivo.tipo = "dicom"
        archivo.estado = "asociado"
        archivo.razon_match = None
        archivo.orthanc_instance_id = resultado.get("orthanc_instance_id")
        archivo.orthanc_study_id = resultado.get("orthanc_study_id")
        archivo.study_instance_uid = resultado.get("study_instance_uid")

        if archivo.study_instance_uid:
            registrar_estudio_dicom_desde_archivo(
                db=db,
                archivo=archivo,
                procedimiento_id=procedimiento_id,
            )

        return True

    except Exception as e:
        archivo.tipo = "dicom"
        archivo.estado = "error_orthanc"
        archivo.razon_match = str(e)[:1500]
        return False


@router.post("/procedimientos/{procedimiento_id}/dicom/reintentar-orthanc")
def reintentar_orthanc_procedimiento_v2(
    procedimiento_id: int,
    db: Session = Depends(get_db),
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

    candidatos = [a for a in archivos if _angio_026_es_dicom_archivo(a)]

    for archivo_db in candidatos:
        if archivo_db.study_instance_uid and archivo_db.orthanc_study_id:
            continue

        ruta = Path(archivo_db.ruta)

        if not ruta.exists():
            archivo_db.tipo = "dicom"
            archivo_db.estado = "error_archivo_no_existe"
            archivo_db.razon_match = f"No existe en disco: {archivo_db.ruta}"
            db.commit()
            continue

        _angio_026_intentar_orthanc(db, archivo_db, procedimiento_id)
        db.commit()

    procedimiento.actualizado_en = datetime.utcnow()
    db.commit()

    return RedirectResponse(url=f"/procedimientos/{procedimiento_id}", status_code=303)


# ============================================================
# ANGIO-038: importar ZIP exportado por NeuroPACS
# ============================================================

@router.get("/importar-caso")
def importar_caso_get(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="importar_caso.html",
        context={}
    )


@router.post("/importar-caso")
async def importar_caso_post(
    request: Request,
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    nombre_zip = _angio_nombre_seguro(archivo.filename)
    data = await archivo.read()

    if not data:
        raise HTTPException(status_code=400, detail="ZIP vacío o no recibido")

    imports_dir = Path(DATA_PATH) / "imports"
    imports_dir.mkdir(parents=True, exist_ok=True)

    ruta_zip = imports_dir / f"{uuid.uuid4().hex}_{nombre_zip}"

    with open(ruta_zip, "wb") as f:
        f.write(data)

    try:
        with zipfile.ZipFile(ruta_zip, "r") as z:
            nombres_zip = set(z.namelist())

            if "case.json" not in nombres_zip:
                raise HTTPException(
                    status_code=400,
                    detail="El ZIP no contiene case.json. No parece ser una exportación NeuroPACS válida."
                )

            case_data = json.loads(z.read("case.json").decode("utf-8"))
            case = case_data.get("case") or {}

            edad_raw = case.get("edad")
            edad_int = int(edad_raw) if edad_raw is not None and str(edad_raw).isdigit() else None

            nota_importacion = f"Importado desde ZIP NeuroPACS: {nombre_zip}"
            notas_previas = case.get("notas_adicionales") or ""
            notas_finales = notas_previas.strip()

            if notas_finales:
                notas_finales += "\n\n"

            notas_finales += nota_importacion

            procedimiento = Procedimiento(
                paciente_nombre=case.get("paciente_nombre"),
                paciente_apellido=case.get("paciente_apellido"),
                paciente_sexo=case.get("paciente_sexo"),
                paciente_fecha_nacimiento=parse_date_or_none(case.get("paciente_fecha_nacimiento")),
                paciente_id=case.get("paciente_id"),
                paciente_mail=case.get("paciente_mail"),
                paciente_telefono=case.get("paciente_telefono"),
                estado_caso=case.get("estado_caso") or "abierto",
                edad=edad_int,
                historia_clinica=case.get("historia_clinica"),
                lugar=case.get("lugar"),
                institucion=case.get("institucion"),
                fecha=parse_date_or_none(case.get("fecha")),
                procedimiento=case.get("procedimiento"),
                diagnostico=case.get("diagnostico"),
                presentacion_clinica=case.get("presentacion_clinica"),
                informe_procedimiento=case.get("informe_procedimiento"),
                complicaciones=case.get("complicaciones"),
                notas_adicionales=notas_finales,
            )

            db.add(procedimiento)
            db.flush()

            asegurar_tag(db, "institucion", procedimiento.institucion)
            asegurar_tag(db, "procedimiento", procedimiento.procedimiento)

            for item in case_data.get("participants", []):
                nombre = (item.get("nombre") or "").strip()
                rol = (item.get("rol") or "").strip()

                if not nombre or not rol:
                    continue

                db.add(
                    ParticipanteProcedimiento(
                        procedimiento_id=procedimiento.id,
                        nombre=nombre,
                        rol=rol,
                        notas=item.get("notas"),
                    )
                )

                asegurar_tag(db, "persona", nombre)
                asegurar_tag(db, "rol_procedimiento", rol)

            for item in case_data.get("materials", []):
                nombre = (item.get("nombre") or "").strip()

                if not nombre:
                    continue

                cantidad_raw = item.get("cantidad")
                cantidad_int = int(cantidad_raw) if cantidad_raw is not None and str(cantidad_raw).isdigit() else 1

                db.add(
                    MaterialProcedimiento(
                        procedimiento_id=procedimiento.id,
                        nombre=nombre,
                        tipo_material=item.get("tipo_material"),
                        cantidad=cantidad_int,
                        notas=item.get("notas"),
                    )
                )

                asegurar_tag(db, "material", nombre)
                asegurar_tag(db, "tipo_material", item.get("tipo_material"))

            for item in case_data.get("dicom_studies", []):
                uid = item.get("study_instance_uid")

                if not uid:
                    continue

                existente = (
                    db.query(EstudioDICOM)
                    .filter(EstudioDICOM.study_instance_uid == uid)
                    .first()
                )

                if existente:
                    if existente.procedimiento_id is None:
                        existente.procedimiento_id = procedimiento.id
                        existente.estado = "asociado"
                    continue

                db.add(
                    EstudioDICOM(
                        procedimiento_id=procedimiento.id,
                        study_instance_uid=uid,
                        orthanc_study_id=item.get("orthanc_study_id"),
                        patient_name=item.get("patient_name"),
                        patient_id=item.get("patient_id"),
                        accession_number=item.get("accession_number"),
                        study_date=item.get("study_date"),
                        modality=item.get("modality"),
                        rol_en_caso=item.get("rol_en_caso"),
                        estado=item.get("estado") or "asociado",
                    )
                )

                if item.get("orthanc_study_id"):
                    procedimiento.dicom_orthanc_id = item.get("orthanc_study_id")

                procedimiento.study_instance_uid = uid

            destino_dir = Path(DATA_PATH) / "web" / str(procedimiento.id)
            destino_dir.mkdir(parents=True, exist_ok=True)

            for item in case_data.get("files", []):
                rel = item.get("ruta_relativa_export")

                if not rel:
                    continue

                rel_path = Path(rel)

                if rel_path.is_absolute() or ".." in rel_path.parts:
                    continue

                rel_zip = str(rel_path).replace("\\", "/")

                if rel_zip not in nombres_zip:
                    continue

                nombre_original = _angio_nombre_seguro(item.get("nombre_original") or rel_path.name)
                destino = destino_dir / f"{uuid.uuid4().hex}_{nombre_original}"

                with z.open(rel_zip) as src, open(destino, "wb") as dst:
                    shutil.copyfileobj(src, dst)

                db.add(
                    Archivo(
                        procedimiento_id=procedimiento.id,
                        tipo=item.get("tipo") or _angio_tipo_por_nombre(nombre_original),
                        categoria=item.get("categoria"),
                        caption=item.get("caption"),
                        origen="import_zip_neuropacs",
                        ruta=str(destino),
                        nombre_original=nombre_original,
                        estado="asociado",
                    )
                )

            db.commit()

            return RedirectResponse(
                url=f"/procedimientos/{procedimiento.id}",
                status_code=303
            )

    except zipfile.BadZipFile:
        db.rollback()
        raise HTTPException(status_code=400, detail="ZIP inválido o corrupto")

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error importando ZIP NeuroPACS: {str(e)}")


# ============================================================
# ANGIO-039: exportar DICOM físicos del caso en ZIP separado
# ============================================================

def _angio_039_nombre_zip_seguro(valor: str | None) -> str:
    valor = str(valor or "sin_nombre")
    limpio = []
    for c in valor:
        if c.isalnum() or c in ["-", "_", "."]:
            limpio.append(c)
        else:
            limpio.append("_")
    return "".join(limpio).strip("_") or "sin_nombre"


@router.get("/procedimientos/{procedimiento_id}/exportar-dicom")
def exportar_procedimiento_dicom_zip(
    procedimiento_id: int,
    db: Session = Depends(get_db),
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

    estudios_dicom = (
        db.query(EstudioDICOM)
        .filter(EstudioDICOM.procedimiento_id == procedimiento_id)
        .order_by(EstudioDICOM.id.asc())
        .all()
    )

    candidatos = []

    for archivo in archivos:
        nombre = f"{archivo.nombre_original or ''} {archivo.ruta or ''}".lower()

        if (
            (archivo.tipo or "").lower() == "dicom"
            or ".dcm" in nombre
            or ".dicom" in nombre
            or ".ima" in nombre
        ):
            candidatos.append(archivo)

    if not candidatos:
        raise HTTPException(
            status_code=404,
            detail="Este caso no tiene archivos DICOM físicos asociados para exportar"
        )

    export_dir = Path(DATA_PATH) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_path = _angio_041_zip_path(export_dir, procedimiento)

    exportados = []
    faltantes = []
    usados = set()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zipf:
        for archivo in candidatos:
            ruta = Path(archivo.ruta)

            if not ruta.exists() or not ruta.is_file():
                faltantes.append({
                    "archivo_id": archivo.id,
                    "ruta": archivo.ruta,
                    "nombre_original": archivo.nombre_original,
                    "estado": archivo.estado,
                    "motivo": "archivo_no_existe_en_disco",
                })
                continue

            study_uid = _angio_039_nombre_zip_seguro(archivo.study_instance_uid or "sin_study_uid")
            nombre_original = _angio_nombre_seguro(archivo.nombre_original or ruta.name)
            arcname_base = f"dicom/{study_uid}/{archivo.id}_{nombre_original}"

            arcname = arcname_base
            contador = 2
            while arcname in usados:
                arcname = f"dicom/{study_uid}/{archivo.id}_{contador}_{nombre_original}"
                contador += 1

            usados.add(arcname)
            zipf.write(ruta, arcname)

            exportados.append({
                "archivo_id": archivo.id,
                "nombre_original": archivo.nombre_original,
                "ruta_zip": arcname,
                "study_instance_uid": archivo.study_instance_uid,
                "orthanc_study_id": archivo.orthanc_study_id,
                "estado": archivo.estado,
            })

        manifest = {
            "schema_version": "1.0.0",
            "app_version": "0.1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "case_id": procedimiento.id,
            "export_type": "dicom_physical_files",
            "contains_dicom_files": True,
            "dicom_files_exported_count": len(exportados),
            "dicom_files_missing_count": len(faltantes),
            "dicom_files_candidates_count": len(candidatos),
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
            "exported_files": exportados,
            "missing_files": faltantes,
        }

        zipf.writestr(
            "manifest_dicom.json",
            json.dumps(manifest, ensure_ascii=False, indent=2)
        )

    if not exportados:
        try:
            zip_path.unlink()
        except Exception:
            pass

        raise HTTPException(
            status_code=404,
            detail="Se encontraron registros DICOM, pero ningún archivo físico existe en disco"
        )

    return FileResponse(
        path=zip_path,
        filename=zip_path.name,
        media_type="application/zip"
    )


# ============================================================
# ANGIO-040: exportar caso completo con DICOM físico
# ============================================================

def _angio_040_nombre_seguro_zip(valor: str | None) -> str:
    valor = str(valor or "sin_nombre")
    limpio = []

    for c in valor:
        if c.isalnum() or c in ["-", "_", "."]:
            limpio.append(c)
        else:
            limpio.append("_")

    return "".join(limpio).strip("_") or "sin_nombre"


@router.get("/procedimientos/{procedimiento_id}/exportar-completo")
def exportar_procedimiento_completo_zip(
    procedimiento_id: int,
    db: Session = Depends(get_db),
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

    export_dir = Path(DATA_PATH) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    zip_path = _angio_041_zip_path(export_dir, procedimiento)

    archivos_exportados = []
    archivos_faltantes = []
    archivos_excluidos = []
    usados = set()

    case_data = {
        "schema_version": "1.0.0",
        "app_version": "0.1.0",
        "export_type": "complete_with_dicom",
        "exported_at": datetime.utcnow().isoformat(),
        "case": {
            "id": procedimiento.id,
            "paciente_nombre": procedimiento.paciente_nombre,
            "paciente_apellido": getattr(procedimiento, "paciente_apellido", None),
            "paciente_sexo": getattr(procedimiento, "paciente_sexo", None),
            "paciente_fecha_nacimiento": str(procedimiento.paciente_fecha_nacimiento) if getattr(procedimiento, "paciente_fecha_nacimiento", None) else None,
            "paciente_id": getattr(procedimiento, "paciente_id", None),
            "paciente_mail": getattr(procedimiento, "paciente_mail", None),
            "paciente_telefono": getattr(procedimiento, "paciente_telefono", None),
            "estado_caso": getattr(procedimiento, "estado_caso", None),
            "edad": procedimiento.edad,
            "historia_clinica": procedimiento.historia_clinica,
            "lugar": procedimiento.lugar,
            "institucion": getattr(procedimiento, "institucion", None),
            "fecha": str(procedimiento.fecha) if procedimiento.fecha else None,
            "procedimiento": procedimiento.procedimiento,
            "diagnostico": procedimiento.diagnostico,
            "presentacion_clinica": procedimiento.presentacion_clinica,
            "localizacion_aneurisma": procedimiento.localizacion_aneurisma,
            "vaina": procedimiento.vaina,
            "cateter": procedimiento.cateter,
            "cateter_intermedio": procedimiento.cateter_intermedio,
            "microcateter": procedimiento.microcateter,
            "guia": procedimiento.guia,
            "microguia": procedimiento.microguia,
            "fd": procedimiento.fd,
            "materiales_usados": procedimiento.materiales_usados,
            "informe_procedimiento": getattr(procedimiento, "informe_procedimiento", None),
            "complicaciones_si_no": procedimiento.complicaciones_si_no,
            "complicaciones": procedimiento.complicaciones,
            "notas_adicionales": procedimiento.notas_adicionales,
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
    }

    md_lines = []
    md_lines.append(f"# Caso {procedimiento.id}")
    md_lines.append("")
    md_lines.append(f"- Paciente: {procedimiento.paciente_nombre or ''} {getattr(procedimiento, 'paciente_apellido', '') or ''}".strip())
    md_lines.append(f"- Historia clínica: {procedimiento.historia_clinica or ''}")
    md_lines.append(f"- Fecha: {procedimiento.fecha or ''}")
    md_lines.append(f"- Institución: {getattr(procedimiento, 'institucion', '') or procedimiento.lugar or ''}")
    md_lines.append(f"- Procedimiento: {procedimiento.procedimiento or ''}")
    md_lines.append("")
    md_lines.append("## Diagnóstico")
    md_lines.append(procedimiento.diagnostico or "")
    md_lines.append("")
    md_lines.append("## Presentación clínica")
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

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zipf:
        zipf.writestr("case.json", json.dumps(case_data, ensure_ascii=False, indent=2))
        zipf.writestr("case.md", "\n".join(md_lines))

        for archivo in archivos:
            ruta = Path(archivo.ruta)
            tipo = (archivo.tipo or "").lower()
            nombre_completo = f"{archivo.nombre_original or ''} {archivo.ruta or ''}".lower()

            es_dicom = (
                tipo == "dicom"
                or ".dcm" in nombre_completo
                or ".dicom" in nombre_completo
                or ".ima" in nombre_completo
            )

            es_zip_original = tipo == "zip"

            if es_zip_original:
                archivos_excluidos.append({
                    "archivo_id": archivo.id,
                    "tipo": archivo.tipo,
                    "nombre_original": archivo.nombre_original,
                    "motivo": "zip_original_excluido_para_evitar_duplicacion",
                    "estado": archivo.estado,
                })
                continue

            if not ruta.exists() or not ruta.is_file():
                archivos_faltantes.append({
                    "archivo_id": archivo.id,
                    "tipo": archivo.tipo,
                    "ruta": archivo.ruta,
                    "nombre_original": archivo.nombre_original,
                    "estado": archivo.estado,
                    "motivo": "archivo_no_existe_en_disco",
                })
                continue

            nombre_original = _angio_nombre_seguro(archivo.nombre_original or ruta.name)

            if es_dicom:
                study_uid = _angio_040_nombre_seguro_zip(archivo.study_instance_uid or "sin_study_uid")
                arcname_base = f"dicom/{study_uid}/{archivo.id}_{nombre_original}"
            else:
                arcname_base = f"files/{archivo.id}_{nombre_original}"

            arcname = arcname_base
            contador = 2

            while arcname in usados:
                if es_dicom:
                    study_uid = _angio_040_nombre_seguro_zip(archivo.study_instance_uid or "sin_study_uid")
                    arcname = f"dicom/{study_uid}/{archivo.id}_{contador}_{nombre_original}"
                else:
                    arcname = f"files/{archivo.id}_{contador}_{nombre_original}"
                contador += 1

            usados.add(arcname)
            zipf.write(ruta, arcname)

            archivos_exportados.append({
                "archivo_id": archivo.id,
                "tipo": archivo.tipo,
                "nombre_original": archivo.nombre_original,
                "ruta_zip": arcname,
                "es_dicom": es_dicom,
                "study_instance_uid": archivo.study_instance_uid,
                "orthanc_study_id": archivo.orthanc_study_id,
                "estado": archivo.estado,
            })

        manifest = {
            "schema_version": "1.0.0",
            "app_version": "0.1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "case_id": procedimiento.id,
            "export_type": "complete_with_dicom",
            "contains_dicom_files": True,
            "exported_files_count": len(archivos_exportados),
            "missing_files_count": len(archivos_faltantes),
            "excluded_files_count": len(archivos_excluidos),
            "exported_files": archivos_exportados,
            "missing_files": archivos_faltantes,
            "excluded_files": archivos_excluidos,
        }

        zipf.writestr("manifest_complete.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return FileResponse(
        path=zip_path,
        filename=zip_path.name,
        media_type="application/zip"
    )


# ============================================================
# ANGIO-041: nombre estándar de exportación ZIP
# Formato: NeuroPACS_ApellidoNombre_AAMMDDHHMM.zip
# ============================================================

def _angio_041_slug_ascii(valor: str | None) -> str:
    valor = str(valor or "").strip()

    if not valor:
        return ""

    valor = unicodedata.normalize("NFKD", valor)
    valor = "".join(c for c in valor if not unicodedata.combining(c))

    limpio = []
    for c in valor:
        if c.isalnum():
            limpio.append(c)
        elif c in [" ", "-", "_", "."]:
            limpio.append("_")

    salida = "".join(limpio)
    salida = re.sub(r"_+", "_", salida).strip("_")

    return salida


def _angio_041_nombre_paciente_export(procedimiento: Procedimiento) -> str:
    apellido = _angio_041_slug_ascii(getattr(procedimiento, "paciente_apellido", None))
    nombre = _angio_041_slug_ascii(getattr(procedimiento, "paciente_nombre", None))

    combinado = f"{apellido}{nombre}".strip("_")

    if combinado:
        return combinado

    return f"Caso{procedimiento.id}"


def _angio_041_zip_path(export_dir: Path, procedimiento: Procedimiento) -> Path:
    paciente = _angio_041_nombre_paciente_export(procedimiento)
    timestamp = datetime.now().strftime("%y%m%d%H%M")
    base = f"NeuroPACS_{paciente}_{timestamp}"
    path = export_dir / f"{base}.zip"

    # Evita sobreescritura si se exporta más de una vez en el mismo minuto.
    if not path.exists():
        return path

    contador = 2
    while True:
        candidato = export_dir / f"{base}_{contador}.zip"
        if not candidato.exists():
            return candidato
        contador += 1


# ============================================================
# ANGIO-042: helper definitivo nombre ZIP
# Formato: NeuroPACS_aa_apellidonombre_AAMMDDHHMM.zip
# aa = año del procedimiento
# ============================================================

def _angio_041_slug_ascii(valor: str | None) -> str:
    import unicodedata as _unicodedata

    valor = str(valor or "").strip().lower()

    if not valor:
        return ""

    valor = _unicodedata.normalize("NFKD", valor)
    valor = "".join(c for c in valor if not _unicodedata.combining(c))

    limpio = []

    for c in valor:
        if c.isalnum():
            limpio.append(c)
        elif c in [" ", "-", "_", "."]:
            limpio.append("_")

    salida = "".join(limpio)

    while "__" in salida:
        salida = salida.replace("__", "_")

    return salida.strip("_")


def _angio_042_anio_procedimiento(procedimiento: Procedimiento) -> str:
    fecha = getattr(procedimiento, "fecha", None)

    if fecha:
        texto = str(fecha)
        if len(texto) >= 4 and texto[:4].isdigit():
            return texto[:4][-2:]

    return datetime.now().strftime("%y")


def _angio_041_nombre_paciente_export(procedimiento: Procedimiento) -> str:
    apellido = _angio_041_slug_ascii(getattr(procedimiento, "paciente_apellido", None))
    nombre = _angio_041_slug_ascii(getattr(procedimiento, "paciente_nombre", None))

    combinado = f"{apellido}{nombre}".strip("_")

    if combinado:
        return combinado

    return f"caso{procedimiento.id}"


def _angio_041_zip_path(export_dir: Path, procedimiento: Procedimiento) -> Path:
    anio_proc = _angio_042_anio_procedimiento(procedimiento)
    paciente = _angio_041_nombre_paciente_export(procedimiento)
    timestamp = datetime.now().strftime("%y%m%d%H%M")

    base = f"NeuroPACS_{anio_proc}_{paciente}_{timestamp}"
    path = export_dir / f"{base}.zip"

    if not path.exists():
        return path

    contador = 2

    while True:
        candidato = export_dir / f"{base}_{contador}.zip"
        if not candidato.exists():
            return candidato
        contador += 1


# ============================================================
# ANGIO-043: repositorio admin para borrar casos y archivos
# ============================================================

def _angio_043_admin_required(request: Request):
    if request.session.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="Solo administradores pueden realizar esta acción")


def _angio_043_unlink_archivo_seguro(ruta_str: str | None):
    if not ruta_str:
        return False

    try:
        ruta = Path(ruta_str)

        if ruta.exists() and ruta.is_file():
            ruta.unlink()
            return True

    except Exception:
        return False

    return False


@router.get("/admin/casos-borrar")
def admin_casos_borrar_get(
    request: Request,
    buscar: str = "",
    db: Session = Depends(get_db),
):
    _angio_043_admin_required(request)

    query = db.query(Procedimiento)

    if buscar:
        filtro = f"%{buscar}%"
        query = query.filter(
            (Procedimiento.paciente_nombre.ilike(filtro)) |
            (Procedimiento.paciente_apellido.ilike(filtro)) |
            (Procedimiento.historia_clinica.ilike(filtro)) |
            (Procedimiento.institucion.ilike(filtro)) |
            (Procedimiento.lugar.ilike(filtro)) |
            (Procedimiento.procedimiento.ilike(filtro))
        )

    procedimientos = query.order_by(Procedimiento.id.desc()).limit(300).all()

    filas = []

    for p in procedimientos:
        archivos_count = db.query(Archivo).filter(Archivo.procedimiento_id == p.id).count()
        dicom_count = db.query(EstudioDICOM).filter(EstudioDICOM.procedimiento_id == p.id).count()
        participantes_count = db.query(ParticipanteProcedimiento).filter(ParticipanteProcedimiento.procedimiento_id == p.id).count()
        materiales_count = db.query(MaterialProcedimiento).filter(MaterialProcedimiento.procedimiento_id == p.id).count()

        filas.append({
            "p": p,
            "archivos_count": archivos_count,
            "dicom_count": dicom_count,
            "participantes_count": participantes_count,
            "materiales_count": materiales_count,
        })

    return templates.TemplateResponse(
        request=request,
        name="admin_casos_borrar.html",
        context={
            "filas": filas,
            "buscar": buscar,
        }
    )


@router.post("/admin/casos-borrar/{procedimiento_id}")
def admin_casos_borrar_post(
    procedimiento_id: int,
    request: Request,
    confirmar: str = Form(""),
    borrar_archivos: str = Form("si"),
    db: Session = Depends(get_db),
):
    _angio_043_admin_required(request)

    if confirmar != "BORRAR":
        raise HTTPException(status_code=400, detail="Confirmación inválida. Debes escribir BORRAR.")

    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Caso no encontrado")

    archivos = db.query(Archivo).filter(Archivo.procedimiento_id == procedimiento_id).all()

    archivos_borrados = 0
    archivos_faltantes = 0

    if borrar_archivos == "si":
        for archivo in archivos:
            ok = _angio_043_unlink_archivo_seguro(archivo.ruta)
            if ok:
                archivos_borrados += 1
            else:
                archivos_faltantes += 1

    # Borrar registros dependientes conocidos.
    db.query(SugerenciaIA).filter(SugerenciaIA.procedimiento_id == procedimiento_id).delete(synchronize_session=False)
    db.query(ParticipanteProcedimiento).filter(ParticipanteProcedimiento.procedimiento_id == procedimiento_id).delete(synchronize_session=False)
    db.query(MaterialProcedimiento).filter(MaterialProcedimiento.procedimiento_id == procedimiento_id).delete(synchronize_session=False)
    db.query(EstudioDICOM).filter(EstudioDICOM.procedimiento_id == procedimiento_id).delete(synchronize_session=False)
    db.query(Archivo).filter(Archivo.procedimiento_id == procedimiento_id).delete(synchronize_session=False)

    db.delete(procedimiento)
    db.commit()

    return RedirectResponse(
        url=f"/admin/casos-borrar?buscar=",
        status_code=303
    )


# ============================================================
# ANGIO-044: galería de imágenes y videos del caso
# ============================================================

@router.get("/procedimientos/{procedimiento_id}/galeria")
def galeria_archivos_caso(
    procedimiento_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    procedimiento = db.query(Procedimiento).filter(Procedimiento.id == procedimiento_id).first()

    if not procedimiento:
        raise HTTPException(status_code=404, detail="Procedimiento no encontrado")

    archivos = (
        db.query(Archivo)
        .filter(
            Archivo.procedimiento_id == procedimiento_id,
            Archivo.tipo.in_(["foto", "video"]),
        )
        .order_by(Archivo.id.asc())
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="galeria.html",
        context={
            "procedimiento": procedimiento,
            "archivos": archivos,
        }
    )

