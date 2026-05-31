from sqlalchemy import text
from database import engine

SQL = """
ALTER TABLE procedimientos
ADD COLUMN IF NOT EXISTS paciente_mail VARCHAR(255);

ALTER TABLE procedimientos
ADD COLUMN IF NOT EXISTS paciente_telefono VARCHAR(100);

ALTER TABLE procedimientos
ADD COLUMN IF NOT EXISTS estado_caso VARCHAR(50) DEFAULT 'abierto';

CREATE INDEX IF NOT EXISTS ix_procedimientos_estado_caso
ON procedimientos (estado_caso);
"""

def migrate():
    with engine.begin() as conn:
        conn.execute(text(SQL))
    print("Migración ANGIO-013 aplicada: estado_caso, paciente_mail, paciente_telefono")

if __name__ == "__main__":
    migrate()
