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
    """

    with engine.begin() as conn:
        conn.execute(text(sql))
