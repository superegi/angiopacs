from pathlib import Path
import os

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from routers.webhook import router as webhook_router
from routers.pacientes import router as pacientes_router
from database import engine, get_db
from models import Base, Procedimiento, ParticipanteProcedimiento

from routers.usuarios import router as usuarios_router

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent

APP_USER = os.getenv("ANGIOPACS_USER", "egidio")
APP_PASSWORD = os.getenv("ANGIOPACS_PASSWORD", "cambia_esta_clave")
SESSION_SECRET = os.getenv("ANGIOPACS_SESSION_SECRET", "cambia_este_secreto_largo")

app = FastAPI(
    title="NeuroPACS",
    description="Biblioteca neurointervencional asistida por IA",
    version="0.1.0"
)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static"
)

templates = Jinja2Templates(directory=BASE_DIR / "templates")

app.include_router(webhook_router)
app.include_router(pacientes_router)
app.include_router(usuarios_router)


def require_login(request: Request):
    if request.session.get("auth") is not True:
        return RedirectResponse(url="/login", status_code=303)
    return None


def normalizar_rol(rol: str | None) -> str:
    """
    Normaliza roles escritos como:
    - primer_operador
    - Primer Operador
    - primer operador
    """
    if not rol:
        return ""

    return (
        rol.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def etiqueta_rol(rol: str | None) -> str:
    rol_norm = normalizar_rol(rol)

    mapa = {
        "primer_operador": "1° operador",
        "segundo_operador": "2° operador",
        "tercer_operador": "3° operador",
        "cuarto_operador": "4° operador",
        "fellow": "Fellow",
        "anestesia": "Anestesia",
    }

    return mapa.get(rol_norm, rol or "")


def construir_resumen_procedimiento(p: Procedimiento) -> dict:
    """
    Construye una representación estable para el listado principal.

    Fuente oficial:
    - paciente: paciente_nombre + paciente_apellido
    - institución: institucion; fallback legacy lugar
    - operadores: participantes_procedimiento; fallback legacy primer_operador/segundo_operador/fellow
    """

    paciente = " ".join(
        parte.strip()
        for parte in [
            p.paciente_nombre or "",
            p.paciente_apellido or "",
        ]
        if parte and parte.strip()
    ).strip() or "Sin nombre"

    institucion = (p.institucion or p.lugar or "").strip()

    roles_operador = {
        "primer_operador",
        "segundo_operador",
        "tercer_operador",
        "cuarto_operador",
        "fellow",
    }

    operadores = []

    for participante in p.participantes or []:
        rol_norm = normalizar_rol(participante.rol)

        if rol_norm in roles_operador:
            operadores.append({
                "rol": etiqueta_rol(participante.rol),
                "nombre": participante.nombre,
            })

    # Fallback legacy solo si no hay participantes estructurados tipo operador/fellow.
    if not operadores:
        if p.primer_operador:
            operadores.append({"rol": "1° operador", "nombre": p.primer_operador})
        if p.segundo_operador:
            operadores.append({"rol": "2° operador", "nombre": p.segundo_operador})
        if p.fellow:
            operadores.append({"rol": "Fellow", "nombre": p.fellow})

    tiene_archivos = bool(p.archivos)
    tiene_dicom = bool(
        p.estudios_dicom
        or p.dicom_orthanc_id
        or p.study_instance_uid
    )

    return {
        "id": p.id,
        "fecha": p.fecha,
        "paciente": paciente,
        "historia_clinica": p.historia_clinica,
        "institucion": institucion,
        "procedimiento": p.procedimiento or "",
        "diagnostico": p.diagnostico or "",
        "operadores": operadores,
        "tiene_archivos": tiene_archivos,
        "tiene_dicom": tiene_dicom,
    }


@app.get("/login")
def login_get(request: Request):
    if request.session.get("auth") is True:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None}
    )


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    BOOTSTRAP_ADMIN = os.getenv("ANGIOPACS_BOOTSTRAP_ADMIN", "true").lower() == "true"

    if BOOTSTRAP_ADMIN and username == APP_USER and password == APP_PASSWORD:
        request.session["auth"] = True
        request.session["user"] = username
        request.session["rol"] = "admin"
        request.session["bootstrap_admin"] = True
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Usuario o contraseña incorrectos"}
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


@app.get("/")
def home(
    request: Request,
    fecha_desde: str = "",
    fecha_hasta: str = "",
    operador: str = "",
    lugar: str = "",
    buscar: str = "",
    db: Session = Depends(get_db)
):
    auth = require_login(request)
    if auth:
        return auth

    query = (
        db.query(Procedimiento)
        .options(
            selectinload(Procedimiento.participantes),
            selectinload(Procedimiento.archivos),
            selectinload(Procedimiento.estudios_dicom),
        )
    )

    if fecha_desde:
        query = query.filter(Procedimiento.fecha >= fecha_desde)

    if fecha_hasta:
        query = query.filter(Procedimiento.fecha <= fecha_hasta)

    if lugar:
        filtro_lugar = f"%{lugar}%"
        query = query.filter(
            or_(
                Procedimiento.institucion.ilike(filtro_lugar),
                Procedimiento.lugar.ilike(filtro_lugar),
            )
        )

    if operador:
        filtro_operador = f"%{operador}%"

        query = (
            query
            .outerjoin(ParticipanteProcedimiento)
            .filter(
                or_(
                    Procedimiento.primer_operador.ilike(filtro_operador),
                    Procedimiento.segundo_operador.ilike(filtro_operador),
                    Procedimiento.fellow.ilike(filtro_operador),
                    Procedimiento.operadores.ilike(filtro_operador),
                    ParticipanteProcedimiento.nombre.ilike(filtro_operador),
                    ParticipanteProcedimiento.rol.ilike(filtro_operador),
                )
            )
            .distinct()
        )

    if buscar:
        filtro_buscar = f"%{buscar}%"
        query = query.filter(
            or_(
                Procedimiento.paciente_nombre.ilike(filtro_buscar),
                Procedimiento.paciente_apellido.ilike(filtro_buscar),
                Procedimiento.paciente_id.ilike(filtro_buscar),
                Procedimiento.historia_clinica.ilike(filtro_buscar),
                Procedimiento.institucion.ilike(filtro_buscar),
                Procedimiento.lugar.ilike(filtro_buscar),
                Procedimiento.diagnostico.ilike(filtro_buscar),
                Procedimiento.procedimiento.ilike(filtro_buscar),
            )
        )

    procedimientos_db = query.order_by(Procedimiento.id.desc()).all()
    procedimientos = [
        construir_resumen_procedimiento(p)
        for p in procedimientos_db
    ]

    return templates.TemplateResponse(
        request=request,
        name="procedimientos.html",
        context={
            "procedimientos": procedimientos,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "operador": operador,
            "lugar": lugar,
            "buscar": buscar,
        }
    )


@app.get("/health")
def health_check():
    return {"status": "online", "service": "NeuroPACS"}
