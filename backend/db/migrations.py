from sqlalchemy import text


def aplicar_migraciones_seguras(engine):
    """
    Migraciones idempotentes.
    No borra datos.
    Se ejecuta al iniciar el backend.
    """

    sql = """
    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS paciente_mail VARCHAR(255);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS paciente_telefono VARCHAR(100);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS estado_caso VARCHAR(50) DEFAULT 'abierto';


    -- ANGIO-CAMPOS-CLINICOS-BASICOS-V1
    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS obra_social VARCHAR(255);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS procedimiento_urgente VARCHAR(20);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS origen_paciente VARCHAR(50);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS tipo_procedimiento VARCHAR(100);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS localizacion TEXT;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS radiacion_dosis VARCHAR(100);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS contraste_ml DOUBLE PRECISION;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS fecha_ingreso DATE;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS fecha_alta DATE;


    -- ANGIO-ESTADO-CASO-V2
    UPDATE procedimientos
    SET estado_caso = 'pendiente_control_ambulatorio'
    WHERE estado_caso = 'pendiente_control';

    UPDATE procedimientos
    SET estado_caso = 'cerrado'
    WHERE estado_caso = 'de_alta';


    -- ANGIO-STROKE-V1
    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_nih_inicial INTEGER;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_nih_llegada INTEGER;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_nih_postprocedimiento INTEGER;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_aspects INTEGER;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_hora_recanalizacion TIMESTAMP WITHOUT TIME ZONE;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_tiempo_puncion_recanalizacion_minutos INTEGER;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_lugar_acceso VARCHAR(100);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_nivel_oclusion TEXT;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_tici VARCHAR(20);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_modalidad_procedimiento VARCHAR(50);

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_imagen_tc BOOLEAN DEFAULT FALSE;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_imagen_rm BOOLEAN DEFAULT FALSE;

    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_imagen_dsa BOOLEAN DEFAULT FALSE;


    -- ANGIO-STROKE-DATOS-CLINICOS-V2
    ALTER TABLE procedimientos
    ADD COLUMN IF NOT EXISTS acv_lateralidad VARCHAR(50);


    -- ANGIO-OCLUSIONES-MULTIPLES-LIMPIO-V1
    CREATE TABLE IF NOT EXISTS sitios_occlusion (
        id SERIAL PRIMARY KEY,
        procedimiento_id INTEGER NOT NULL REFERENCES procedimientos(id) ON DELETE CASCADE,
        lateralidad VARCHAR(50),
        sitio_anatomico VARCHAR(255),
        metodo_recanalizacion VARCHAR(50),
        tici VARCHAR(20)
    );

    CREATE INDEX IF NOT EXISTS ix_sitios_occlusion_procedimiento_id
    ON sitios_occlusion (procedimiento_id);


    -- ANGIO-PARTICIPANTES-MATERIALES-FORCE-V3
    ALTER TABLE IF EXISTS participantes_procedimiento
    ADD COLUMN IF NOT EXISTS nombre VARCHAR(255);

    ALTER TABLE IF EXISTS participantes_procedimiento
    ADD COLUMN IF NOT EXISTS rol VARCHAR(80);

    ALTER TABLE IF EXISTS participantes_procedimiento
    ADD COLUMN IF NOT EXISTS es_fellow BOOLEAN DEFAULT FALSE;

    ALTER TABLE IF EXISTS participantes_procedimiento
    ADD COLUMN IF NOT EXISTS notas TEXT;

    ALTER TABLE IF EXISTS archivos
    ADD COLUMN IF NOT EXISTS tipo VARCHAR(120);

    ALTER TABLE IF EXISTS archivos
    ADD COLUMN IF NOT EXISTS nombre VARCHAR(255);

    ALTER TABLE IF EXISTS archivos
    ADD COLUMN IF NOT EXISTS tamano VARCHAR(120);

    ALTER TABLE IF EXISTS archivos
    ADD COLUMN IF NOT EXISTS marca VARCHAR(120);

    ALTER TABLE IF EXISTS archivos
    ADD COLUMN IF NOT EXISTS notas TEXT;


    -- ANGIO-MATERIALES-DEDICADOS-V4
    CREATE TABLE IF NOT EXISTS materiales_procedimiento (
        id SERIAL PRIMARY KEY,
        procedimiento_id INTEGER NOT NULL REFERENCES procedimientos(id) ON DELETE CASCADE,
        tipo VARCHAR(120),
        nombre VARCHAR(255),
        tamano VARCHAR(120),
        marca VARCHAR(120),
        notas TEXT
    );


    -- ANGIO-MATERIALPROCEDIMIENTO-FIX-TIPO-V5
    ALTER TABLE IF EXISTS materiales_procedimiento
    ADD COLUMN IF NOT EXISTS tipo VARCHAR(120);

    ALTER TABLE IF EXISTS materiales_procedimiento
    ADD COLUMN IF NOT EXISTS tamano VARCHAR(120);

    ALTER TABLE IF EXISTS materiales_procedimiento
    ADD COLUMN IF NOT EXISTS marca VARCHAR(120);

    ALTER TABLE IF EXISTS materiales_procedimiento
    ADD COLUMN IF NOT EXISTS tipo_material VARCHAR(100);

    ALTER TABLE IF EXISTS materiales_procedimiento
    ADD COLUMN IF NOT EXISTS cantidad INTEGER DEFAULT 1;

    CREATE INDEX IF NOT EXISTS ix_materiales_procedimiento_procedimiento_id
    ON materiales_procedimiento (procedimiento_id);

    CREATE INDEX IF NOT EXISTS ix_procedimientos_estado_caso
    ON procedimientos (estado_caso);

    ALTER TABLE archivos
    ALTER COLUMN estado TYPE TEXT;

    ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN DEFAULT TRUE;

    ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS password_temporal BOOLEAN DEFAULT TRUE;

    ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS ultimo_login_en TIMESTAMP WITHOUT TIME ZONE;

    ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS ultimo_login_ip VARCHAR(100);

    ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS perfil_actualizado_en TIMESTAMP WITHOUT TIME ZONE;

    CREATE INDEX IF NOT EXISTS ix_usuarios_ultimo_login_en
    ON usuarios (ultimo_login_en);

    CREATE TABLE IF NOT EXISTS auditoria_eventos (
        id SERIAL PRIMARY KEY,
        creado_en TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
        usuario VARCHAR(255),
        ip VARCHAR(100),
        accion VARCHAR(100) NOT NULL,
        tarea_id VARCHAR(100),
        tarea VARCHAR(255),
        estado VARCHAR(100),
        caso_id INTEGER,
        archivo_nombre TEXT,
        archivo_bytes INTEGER,
        detalle TEXT
    );

    ALTER TABLE auditoria_eventos
    ADD COLUMN IF NOT EXISTS dispositivo VARCHAR(50);

    ALTER TABLE auditoria_eventos
    ADD COLUMN IF NOT EXISTS user_agent TEXT;

    ALTER TABLE auditoria_eventos
    ADD COLUMN IF NOT EXISTS archivo_nombre TEXT;

    ALTER TABLE auditoria_eventos
    ADD COLUMN IF NOT EXISTS archivo_bytes INTEGER;


    ALTER TABLE auditoria_eventos
    ADD COLUMN IF NOT EXISTS client_timezone VARCHAR(100);

    ALTER TABLE auditoria_eventos
    ADD COLUMN IF NOT EXISTS client_utc_offset_minutes INTEGER;

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_client_timezone
    ON auditoria_eventos (client_timezone);

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_dispositivo
    ON auditoria_eventos (dispositivo);

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_creado_en
    ON auditoria_eventos (creado_en);

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_usuario
    ON auditoria_eventos (usuario);

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_accion
    ON auditoria_eventos (accion);

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_tarea_id
    ON auditoria_eventos (tarea_id);

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_tarea
    ON auditoria_eventos (tarea);

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_estado
    ON auditoria_eventos (estado);

    CREATE INDEX IF NOT EXISTS ix_auditoria_eventos_caso_id
    ON auditoria_eventos (caso_id);
    """

    with engine.begin() as conn:
        conn.execute(text(sql))
