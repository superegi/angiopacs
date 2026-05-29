from sqlalchemy.orm import Session
from datetime import datetime
import models

def crear_procedimiento(db: Session, datos: dict):
    procedimiento = models.Procedimiento(
        lugar=datos.get("lugar"),
        historia_clinica=datos.get("historia_clinica"),
        paciente_nombre=datos.get("paciente_nombre"),
        edad=datos.get("edad"),
        fecha=datos.get("fecha"),
        procedimiento=datos.get("procedimiento"),
        diagnostico=datos.get("diagnostico"),
        presentacion_clinica=datos.get("presentacion_clinica"),
        localizacion_aneurisma=datos.get("localizacion_aneurisma"),
    )
    db.add(procedimiento)
    db.commit()
    db.refresh(procedimiento)
    return procedimiento

def crear_procedimiento_basico(db: Session, paciente_nombre: str | None, historia_clinica: str | None):
    procedimiento = models.Procedimiento(
        paciente_nombre=paciente_nombre,
        historia_clinica=historia_clinica,
    )
    db.add(procedimiento)
    db.commit()
    db.refresh(procedimiento)
    return procedimiento

def obtener_procedimiento(db: Session, procedimiento_id: int):
    return db.query(models.Procedimiento).filter(models.Procedimiento.id == procedimiento_id).first()

def listar_ultimos_procedimientos(db: Session, limite: int = 5):
    return db.query(models.Procedimiento).order_by(models.Procedimiento.id.desc()).limit(limite).all()

def obtener_sesion_activa(db: Session, telegram_chat_id: str):
    return (
        db.query(models.SesionCarga)
        .filter(
            models.SesionCarga.telegram_chat_id == telegram_chat_id,
            models.SesionCarga.estado == "activa"
        )
        .order_by(models.SesionCarga.id.desc())
        .first()
    )

def cerrar_sesiones_activas(db: Session, telegram_chat_id: str):
    sesiones = (
        db.query(models.SesionCarga)
        .filter(
            models.SesionCarga.telegram_chat_id == telegram_chat_id,
            models.SesionCarga.estado == "activa"
        )
        .all()
    )
    for s in sesiones:
        s.estado = "cerrada"
        s.actualizado_en = datetime.utcnow()
    db.commit()

def crear_sesion_carga(db: Session, telegram_chat_id: str, procedimiento_id: int):
    cerrar_sesiones_activas(db, telegram_chat_id)

    sesion = models.SesionCarga(
        telegram_chat_id=telegram_chat_id,
        procedimiento_id=procedimiento_id,
        estado="activa"
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion

def crear_archivo(
    db: Session,
    ruta: str,
    tipo: str,
    origen: str,
    procedimiento_id: int | None = None,
    telegram_file_id: str | None = None,
    telegram_chat_id: str | None = None,
    estado: str = "pendiente",
):
    archivo = models.Archivo(
        procedimiento_id=procedimiento_id,
        tipo=tipo,
        origen=origen,
        ruta=ruta,
        telegram_file_id=telegram_file_id,
        telegram_chat_id=telegram_chat_id,
        estado=estado,
    )
    db.add(archivo)
    db.commit()
    db.refresh(archivo)
    return archivo

# =========================
# CRUD estructurado ANGIO-002
# =========================

def crear_participante(
    db: Session,
    procedimiento_id: int,
    nombre: str,
    rol: str,
    notas: str | None = None,
):
    participante = models.ParticipanteProcedimiento(
        procedimiento_id=procedimiento_id,
        nombre=nombre,
        rol=rol,
        notas=notas,
    )
    db.add(participante)
    db.commit()
    db.refresh(participante)
    return participante


def listar_participantes(db: Session, procedimiento_id: int):
    return (
        db.query(models.ParticipanteProcedimiento)
        .filter(models.ParticipanteProcedimiento.procedimiento_id == procedimiento_id)
        .order_by(models.ParticipanteProcedimiento.id.asc())
        .all()
    )


def crear_material(
    db: Session,
    procedimiento_id: int,
    nombre: str,
    tipo_material: str | None = None,
    cantidad: int = 1,
    notas: str | None = None,
):
    material = models.MaterialProcedimiento(
        procedimiento_id=procedimiento_id,
        nombre=nombre,
        tipo_material=tipo_material,
        cantidad=cantidad,
        notas=notas,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


def listar_materiales(db: Session, procedimiento_id: int):
    return (
        db.query(models.MaterialProcedimiento)
        .filter(models.MaterialProcedimiento.procedimiento_id == procedimiento_id)
        .order_by(models.MaterialProcedimiento.id.asc())
        .all()
    )


def crear_estudio_dicom(
    db: Session,
    study_instance_uid: str,
    orthanc_study_id: str | None = None,
    procedimiento_id: int | None = None,
    patient_name: str | None = None,
    patient_id: str | None = None,
    accession_number: str | None = None,
    study_date: str | None = None,
    modality: str | None = None,
    rol_en_caso: str | None = None,
    estado: str = "huerfano",
):
    existente = (
        db.query(models.EstudioDICOM)
        .filter(models.EstudioDICOM.study_instance_uid == study_instance_uid)
        .first()
    )

    if existente:
        if orthanc_study_id is not None:
            existente.orthanc_study_id = orthanc_study_id
        if procedimiento_id is not None:
            existente.procedimiento_id = procedimiento_id
            existente.estado = "asociado"
        if patient_name is not None:
            existente.patient_name = patient_name
        if patient_id is not None:
            existente.patient_id = patient_id
        if accession_number is not None:
            existente.accession_number = accession_number
        if study_date is not None:
            existente.study_date = study_date
        if modality is not None:
            existente.modality = modality
        if rol_en_caso is not None:
            existente.rol_en_caso = rol_en_caso

        existente.actualizado_en = datetime.utcnow()
        db.commit()
        db.refresh(existente)
        return existente

    estudio = models.EstudioDICOM(
        procedimiento_id=procedimiento_id,
        study_instance_uid=study_instance_uid,
        orthanc_study_id=orthanc_study_id,
        patient_name=patient_name,
        patient_id=patient_id,
        accession_number=accession_number,
        study_date=study_date,
        modality=modality,
        rol_en_caso=rol_en_caso,
        estado="asociado" if procedimiento_id else estado,
    )
    db.add(estudio)
    db.commit()
    db.refresh(estudio)
    return estudio


def listar_estudios_dicom(
    db: Session,
    procedimiento_id: int | None = None,
    solo_huerfanos: bool = False,
):
    query = db.query(models.EstudioDICOM)

    if procedimiento_id is not None:
        query = query.filter(models.EstudioDICOM.procedimiento_id == procedimiento_id)

    if solo_huerfanos:
        query = query.filter(models.EstudioDICOM.procedimiento_id.is_(None))

    return query.order_by(models.EstudioDICOM.id.desc()).all()


def asociar_estudio_dicom(
    db: Session,
    estudio_id: int,
    procedimiento_id: int,
    rol_en_caso: str | None = None,
):
    estudio = db.query(models.EstudioDICOM).filter(models.EstudioDICOM.id == estudio_id).first()
    if not estudio:
        return None

    estudio.procedimiento_id = procedimiento_id
    estudio.estado = "asociado"

    if rol_en_caso is not None:
        estudio.rol_en_caso = rol_en_caso

    estudio.actualizado_en = datetime.utcnow()
    db.commit()
    db.refresh(estudio)
    return estudio


def crear_tag(
    db: Session,
    tipo: str,
    nombre: str,
    descripcion: str | None = None,
):
    existente = (
        db.query(models.RepositorioTag)
        .filter(
            models.RepositorioTag.tipo == tipo,
            models.RepositorioTag.nombre == nombre,
        )
        .first()
    )

    if existente:
        return existente

    tag = models.RepositorioTag(
        tipo=tipo,
        nombre=nombre,
        descripcion=descripcion,
        activo=True,
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def listar_tags(
    db: Session,
    tipo: str | None = None,
    activos: bool = True,
):
    query = db.query(models.RepositorioTag)

    if tipo is not None:
        query = query.filter(models.RepositorioTag.tipo == tipo)

    if activos:
        query = query.filter(models.RepositorioTag.activo == True)

    return query.order_by(models.RepositorioTag.tipo.asc(), models.RepositorioTag.nombre.asc()).all()


def crear_sugerencia_ia(
    db: Session,
    tarea: str,
    procedimiento_id: int | None = None,
    archivo_id: int | None = None,
    campo_destino: str | None = None,
    valor_sugerido: str | None = None,
    confianza: float | None = None,
    razon: str | None = None,
):
    sugerencia = models.SugerenciaIA(
        procedimiento_id=procedimiento_id,
        archivo_id=archivo_id,
        tarea=tarea,
        campo_destino=campo_destino,
        valor_sugerido=valor_sugerido,
        confianza=confianza,
        razon=razon,
        estado="pendiente",
    )
    db.add(sugerencia)
    db.commit()
    db.refresh(sugerencia)
    return sugerencia


def listar_sugerencias_ia(
    db: Session,
    procedimiento_id: int | None = None,
    estado: str | None = "pendiente",
):
    query = db.query(models.SugerenciaIA)

    if procedimiento_id is not None:
        query = query.filter(models.SugerenciaIA.procedimiento_id == procedimiento_id)

    if estado is not None:
        query = query.filter(models.SugerenciaIA.estado == estado)

    return query.order_by(models.SugerenciaIA.id.desc()).all()


def resolver_sugerencia_ia(
    db: Session,
    sugerencia_id: int,
    estado: str,
):
    sugerencia = db.query(models.SugerenciaIA).filter(models.SugerenciaIA.id == sugerencia_id).first()

    if not sugerencia:
        return None

    sugerencia.estado = estado
    sugerencia.resuelto_en = datetime.utcnow()

    db.commit()
    db.refresh(sugerencia)
    return sugerencia

