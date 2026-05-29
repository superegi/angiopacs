from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Procedimiento(Base):
    __tablename__ = "procedimientos"

    id = Column(Integer, primary_key=True, index=True)

    # Identificacion del caso / paciente
    paciente_nombre = Column(String(255), index=True, nullable=True)
    paciente_apellido = Column(String(255), index=True, nullable=True)
    paciente_sexo = Column(String(50), nullable=True)
    paciente_fecha_nacimiento = Column(Date, nullable=True)
    paciente_id = Column(String(100), index=True, nullable=True)
    edad = Column(Integer, nullable=True)

    # Datos del procedimiento
    lugar = Column(String(255), nullable=True)
    institucion = Column(String(255), nullable=True)
    historia_clinica = Column(String(100), index=True, nullable=True)
    fecha = Column(Date, nullable=True)
    procedimiento = Column(String(255), nullable=True)
    diagnostico = Column(Text, nullable=True)

    # Campos legacy, se mantienen temporalmente para compatibilidad
    primer_operador = Column(String(255), nullable=True)
    segundo_operador = Column(String(255), nullable=True)
    fellow = Column(String(255), nullable=True)
    operadores = Column(Text, nullable=True)

    # Historia
    app = Column(Text, nullable=True)
    presentacion_clinica = Column(Text, nullable=True)
    signos_sintomas = Column(Text, nullable=True)
    localizacion_aneurisma = Column(Text, nullable=True)

    # Historia ACV / trombectomia
    acv_activado = Column(Boolean, default=False)
    hora_inicio_sintomas = Column(DateTime, nullable=True)
    hora_consulta_urgencia = Column(DateTime, nullable=True)
    hora_neuroimagen = Column(DateTime, nullable=True)
    hora_llegada_neuroteam_angio = Column(DateTime, nullable=True)
    hora_llegada_paciente_angio = Column(DateTime, nullable=True)
    hora_puncion_femoral = Column(DateTime, nullable=True)
    hora_apertura_arteria = Column(DateTime, nullable=True)
    hora_fin_procedimiento = Column(DateTime, nullable=True)

    # Campos legacy de materiales, se mantienen temporalmente
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

    # Resultado / informe
    informe_procedimiento = Column(Text, nullable=True)
    complicaciones_si_no = Column(String(20), nullable=True)
    complicaciones = Column(Text, nullable=True)
    medicacion = Column(Text, nullable=True)
    evolucion = Column(Text, nullable=True)
    notas_adicionales = Column(Text, nullable=True)

    # DICOM legacy
    dicom_orthanc_id = Column(String(100), nullable=True)
    study_instance_uid = Column(String(255), nullable=True)

    # Otros legacy
    link_ppt = Column(Text, nullable=True)
    fecha_control = Column(String(100), nullable=True)
    imagen_control = Column(Text, nullable=True)

    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow)

    archivos = relationship("Archivo", back_populates="procedimiento", cascade="all, delete-orphan")
    participantes = relationship("ParticipanteProcedimiento", back_populates="procedimiento", cascade="all, delete-orphan")
    materiales = relationship("MaterialProcedimiento", back_populates="procedimiento", cascade="all, delete-orphan")
    estudios_dicom = relationship("EstudioDICOM", back_populates="procedimiento")
    sugerencias_ia = relationship("SugerenciaIA", back_populates="procedimiento", cascade="all, delete-orphan")


class Archivo(Base):
    __tablename__ = "archivos"

    id = Column(Integer, primary_key=True, index=True)

    procedimiento_id = Column(Integer, ForeignKey("procedimientos.id"), nullable=True)
    procedimiento = relationship("Procedimiento", back_populates="archivos")

    tipo = Column(String(50), nullable=True)
    categoria = Column(String(100), nullable=True)
    origen = Column(String(50), nullable=True)
    ruta = Column(Text, nullable=False)

    telegram_file_id = Column(Text, nullable=True)
    telegram_chat_id = Column(String(100), nullable=True)
    nombre_original = Column(Text, nullable=True)

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

    estado = Column(String(50), default="pendiente")
    creado_en = Column(DateTime, default=datetime.utcnow)


class ParticipanteProcedimiento(Base):
    __tablename__ = "participantes_procedimiento"

    id = Column(Integer, primary_key=True, index=True)

    procedimiento_id = Column(Integer, ForeignKey("procedimientos.id"), nullable=False)
    procedimiento = relationship("Procedimiento", back_populates="participantes")

    nombre = Column(String(255), nullable=False)
    rol = Column(String(100), nullable=False)
    notas = Column(Text, nullable=True)

    creado_en = Column(DateTime, default=datetime.utcnow)


class MaterialProcedimiento(Base):
    __tablename__ = "materiales_procedimiento"

    id = Column(Integer, primary_key=True, index=True)

    procedimiento_id = Column(Integer, ForeignKey("procedimientos.id"), nullable=False)
    procedimiento = relationship("Procedimiento", back_populates="materiales")

    nombre = Column(String(255), nullable=False)
    tipo_material = Column(String(100), nullable=True)
    cantidad = Column(Integer, default=1)
    notas = Column(Text, nullable=True)

    creado_en = Column(DateTime, default=datetime.utcnow)


class EstudioDICOM(Base):
    __tablename__ = "estudios_dicom"

    id = Column(Integer, primary_key=True, index=True)

    procedimiento_id = Column(Integer, ForeignKey("procedimientos.id"), nullable=True)
    procedimiento = relationship("Procedimiento", back_populates="estudios_dicom")

    study_instance_uid = Column(String(255), unique=True, index=True, nullable=False)
    orthanc_study_id = Column(String(100), index=True, nullable=True)

    patient_name = Column(String(255), nullable=True)
    patient_id = Column(String(100), index=True, nullable=True)
    accession_number = Column(String(100), nullable=True)
    study_date = Column(String(50), nullable=True)
    modality = Column(String(50), nullable=True)

    rol_en_caso = Column(String(100), nullable=True)
    estado = Column(String(50), default="huerfano")

    creado_en = Column(DateTime, default=datetime.utcnow)
    actualizado_en = Column(DateTime, default=datetime.utcnow)


class RepositorioTag(Base):
    __tablename__ = "repositorios_tags"

    id = Column(Integer, primary_key=True, index=True)

    tipo = Column(String(100), index=True, nullable=False)
    nombre = Column(String(255), index=True, nullable=False)
    descripcion = Column(Text, nullable=True)
    activo = Column(Boolean, default=True)

    creado_en = Column(DateTime, default=datetime.utcnow)


class SugerenciaIA(Base):
    __tablename__ = "sugerencias_ia"

    id = Column(Integer, primary_key=True, index=True)

    procedimiento_id = Column(Integer, ForeignKey("procedimientos.id"), nullable=True)
    procedimiento = relationship("Procedimiento", back_populates="sugerencias_ia")

    archivo_id = Column(Integer, ForeignKey("archivos.id"), nullable=True)

    tarea = Column(String(100), nullable=False)
    campo_destino = Column(String(255), nullable=True)
    valor_sugerido = Column(Text, nullable=True)
    confianza = Column(Float, nullable=True)
    razon = Column(Text, nullable=True)

    estado = Column(String(50), default="pendiente")
    creado_en = Column(DateTime, default=datetime.utcnow)
    resuelto_en = Column(DateTime, nullable=True)


class SesionCarga(Base):
    __tablename__ = "sesiones_carga"

    id = Column(Integer, primary_key=True, index=True)

    telegram_chat_id = Column(String(100), index=True, nullable=False)
    procedimiento_id = Column(Integer, ForeignKey("procedimientos.id"), nullable=True)

    estado = Column(String(50), default="activa")
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
