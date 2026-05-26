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
