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

    CREATE INDEX IF NOT EXISTS ix_procedimientos_estado_caso
    ON procedimientos (estado_caso);

    ALTER TABLE archivos
    ALTER COLUMN estado TYPE TEXT;

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
