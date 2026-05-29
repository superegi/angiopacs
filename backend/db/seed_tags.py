from database import SessionLocal
from models import RepositorioTag

SEEDS = {
    "rol_procedimiento": [
        "primer_operador",
        "segundo_operador",
        "tercer_operador",
        "fellow",
        "anestesia",
        "enfermeria",
        "tecnologo",
        "otro",
    ],
    "tipo_material": [
        "vaina",
        "cateter",
        "cateter_intermedio",
        "microcateter",
        "microguia",
        "guia",
        "balon",
        "stent",
        "coil",
        "embolizante",
        "dispositivo_trombectomia",
        "otro",
    ],
    "procedimiento": [
        "angiografia_diagnostica",
        "embolizacion_aneurisma",
        "coils",
        "stent",
        "diversor_flujo",
        "trombectomia",
        "angioplastia",
        "embolizacion_mav",
        "embolizacion_fistula",
        "otro",
    ],
    "institucion": [],
    "persona": [],
    "material": [],
}

def seed_tags():
    db = SessionLocal()
    try:
        creados = 0

        for tipo, nombres in SEEDS.items():
            for nombre in nombres:
                existe = (
                    db.query(RepositorioTag)
                    .filter(
                        RepositorioTag.tipo == tipo,
                        RepositorioTag.nombre == nombre,
                    )
                    .first()
                )

                if existe:
                    continue

                db.add(
                    RepositorioTag(
                        tipo=tipo,
                        nombre=nombre,
                        activo=True,
                    )
                )
                creados += 1

        db.commit()
        print(f"Seed completado. Tags creados: {creados}")

    finally:
        db.close()

if __name__ == "__main__":
    seed_tags()
