from sqlalchemy import Column, Integer, String, Date, Text, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Procedimiento(Base):
    __tablename__ = "procedimientos"

    id = Column(Integer, primary_key=True, index=True)

    lugar = Column(String(255), nullable=True)
    historia_clinica = Column(String(100), index=True, nullable=True)
    paciente_nombre = Column(String(255), index=True, nullable=True)
    edad = Column(Integer, nullable=True)
    fecha = Column(Date, nullable=True)

    primer_operador = Column(String(255), nullable=True)
    segundo_operador = Column(String(255), nullable=True)
    fellow = Column(String(255), nullable=True)
    operadores = Column(Text, nullable=True)

    app = Column(Text, nullable=True)
    presentacion_clinica = Column(Text, nullable=True)
    signos_sintomas = Column(Text, nullable=True)
    diagnostico = Column(Text, nullable=True)
    procedimiento = Column(String(255), nullable=True)
    localizacion_aneurisma = Column(Text, nullable=True)

    vaina = Column(String(100), nullable=True)
    introductor = Column(String(255), nullable=True)
    cateter = Column(String(255), nullable=True)
    cateter_intermedio = Column(String(255), nullable=True)
    microcateter = Column(String(255), nullable=True)
    guia = Column(String(255), nullable=True)
    microguia = Column(String(255), nullable=True)
    dispositivo = Column(Text, nullable=True)
    fd = Column(String(255), nullable=True)
    materiales_adicionales = Column(Text, nullable=True)
    materiales_usados = Column(Text, nullable=True)
    navegacion = Column(Text, nullable=True)

    complicaciones = Column(Text, nullable=True)
    medicacion = Column(Text, nullable=True)
    evolucion = Column(Text, nullable=True)
    notas_adicionales = Column(Text, nullable=True)

    dicom_orthanc_id = Column(String(100), nullable=True)
    study_instance_uid = Column(String(255), nullable=True)

    link_ppt = Column(Text, nullable=True)
    fecha_control = Column(String(100), nullable=True)
    imagen_control = Column(Text, nullable=True)

    creado_en = Column(DateTime, default=datetime.utcnow)

    archivos = relationship("Archivo", back_populates="procedimiento")


class Archivo(Base):
    __tablename__ = "archivos"

    id = Column(Integer, primary_key=True, index=True)

    procedimiento_id = Column(Integer, ForeignKey("procedimientos.id"), nullable=True)
    procedimiento = relationship("Procedimiento", back_populates="archivos")

    tipo = Column(String(50), nullable=True)       # foto, video, dicom, pdf, texto
    origen = Column(String(50), nullable=True)     # telegram, web, orthanc, manual
    ruta = Column(Text, nullable=False)

    telegram_file_id = Column(Text, nullable=True)
    telegram_chat_id = Column(String(100), nullable=True)
    nombre_original = Column(Text, nullable=True)
    orthanc_instance_id = Column(String(100), nullable=True)
    orthanc_study_id = Column(String(100), nullable=True)
    study_instance_uid = Column(String(255), nullable=True)
    orthanc_instance_id = Column(String(100), nullable=True)
    orthanc_study_id = Column(String(100), nullable=True)
    study_instance_uid = Column(String(255), nullable=True)

    orthanc_instance_id = Column(String(100), nullable=True)
    orthanc_study_id = Column(String(100), nullable=True)
    study_instance_uid = Column(String(255), nullable=True)

    texto_extraido = Column(Text, nullable=True)
    paciente_sugerido = Column(String(255), nullable=True)
    historia_clinica_sugerida = Column(String(100), nullable=True)
    fecha_sugerida = Column(String(100), nullable=True)
    material_sugerido = Column(Text, nullable=True)

    confianza_match = Column(Float, nullable=True)
    razon_match = Column(Text, nullable=True)

    estado = Column(String(50), default="pendiente")  # pendiente, asociado, descartado
    creado_en = Column(DateTime, default=datetime.utcnow)


class SesionCarga(Base):
    __tablename__ = "sesiones_carga"

    id = Column(Integer, primary_key=True, index=True)

    telegram_chat_id = Column(String(100), index=True, nullable=False)
    procedimiento_id = Column(Integer, ForeignKey("procedimientos.id"), nullable=True)

    estado = Column(String(50), default="activa")  # activa, cerrada
    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow)


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    nombre = Column(String(255), nullable=True)
    pais = Column(String(100), nullable=True)
    ciudad = Column(String(100), nullable=True)
    edad = Column(Integer, nullable=True)

    mail = Column(String(255), nullable=True)

    especialidad = Column(String(100), nullable=True)
    rol = Column(String(50), default="comun")

    activo = Column(String(10), default="si")

    creado_en = Column(DateTime, default=datetime.utcnow)
