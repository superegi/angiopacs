from pathlib import Path
import os
import time
from datetime import datetime

from fastapi import FastAPI, Request, Depends, Form
from passlib.context import CryptContext
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from routers.webhook import router as webhook_router
from routers.pacientes import router as pacientes_router
from database import engine, get_db
from db.migrations import aplicar_migraciones_seguras
from models import Base, Procedimiento, ParticipanteProcedimiento, Usuario

from routers.usuarios import router as usuarios_router
from routers.orthanc_gateway import router as orthanc_gateway_router

Base.metadata.create_all(bind=engine)
aplicar_migraciones_seguras(engine)

BASE_DIR = Path(__file__).resolve().parent

APP_USER = os.getenv("ANGIOPACS_USER", "egidio")
APP_PASSWORD = os.getenv("ANGIOPACS_PASSWORD", "cambia_esta_clave")
SESSION_SECRET = os.getenv("ANGIOPACS_SESSION_SECRET", "cambia_este_secreto_largo")

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)

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
app.include_router(orthanc_gateway_router)


def require_login(request: Request):
    if request.session.get("auth") is not True:
        return RedirectResponse(url="/login", status_code=303)

    path = request.url.path

    rutas_libres = (
        "/logout",
        "/mi-perfil",
        "/static",
        "/health",
        "/favicon.ico",
    )

    if any(path == r or path.startswith(r + "/") for r in rutas_libres):
        return None

    if (
        request.session.get("bootstrap_admin") is not True
        and request.session.get("must_change_password") is True
    ):
        return RedirectResponse(url="/mi-perfil?forzar_password=1", status_code=303)

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
        "estado_caso": p.estado_caso or "abierto",
    }



@app.get("/casos-activos")
def casos_activos(
    request: Request,
    db: Session = Depends(get_db)
):
    auth = require_login(request)
    if auth:
        return auth

    estados_visibles = ["abierto", "hospitalizado", "pendiente_control"]

    procedimientos_db = (
        db.query(Procedimiento)
        .options(
            selectinload(Procedimiento.participantes),
            selectinload(Procedimiento.archivos),
            selectinload(Procedimiento.estudios_dicom),
        )
        .filter(Procedimiento.estado_caso.in_(estados_visibles))
        .order_by(Procedimiento.fecha.desc().nullslast(), Procedimiento.id.desc())
        .all()
    )

    procedimientos = [construir_resumen_procedimiento(p) for p in procedimientos_db]

    conteos = {
        "abierto": 0,
        "hospitalizado": 0,
        "pendiente_control": 0,
    }

    for p in procedimientos:
        estado = p.get("estado_caso") or "abierto"
        if estado in conteos:
            conteos[estado] += 1

    return templates.TemplateResponse(
        request=request,
        name="casos_activos.html",
        context={
            "procedimientos": procedimientos,
            "conteos": conteos,
        }
    )

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
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    login_started = time.monotonic()

    username = (username or "").strip()
    password = password or ""

    try:
        login_delay = float(os.getenv("ANGIOPACS_LOGIN_DELAY_SECONDS", "3"))
    except ValueError:
        login_delay = 3.0

    login_delay = max(0.0, min(login_delay, 10.0))

    def aplicar_delay_login():
        elapsed = time.monotonic() - login_started
        restante = login_delay - elapsed
        if restante > 0:
            time.sleep(restante)

    def usuario_activo(valor):
        if valor is True:
            return True
        texto = str(valor or "").strip().lower()
        return texto in ["si", "sí", "true", "1", "activo", "active"]

    bootstrap_admin = os.getenv("ANGIOPACS_BOOTSTRAP_ADMIN", "true").lower() == "true"

    # 1) Usuario bootstrap desde .env
    if bootstrap_admin and username == APP_USER and password == APP_PASSWORD:
        aplicar_delay_login()

        request.session["auth"] = True
        request.session["user"] = username
        request.session["rol"] = "admin"
        request.session["bootstrap_admin"] = True
        request.session["must_change_password"] = False
        request.session["ultimo_login_previo"] = ""

        return RedirectResponse(url="/", status_code=303)

    # 2) Usuarios reales creados en la base de datos
    usuario = (
        db.query(Usuario)
        .filter(Usuario.username == username)
        .first()
    )

    password_ok = False

    if usuario and usuario.password_hash:
        try:
            password_ok = pwd_context.verify(password, usuario.password_hash)
        except Exception:
            password_ok = False

    if usuario and usuario_activo(usuario.activo) and password_ok:
        aplicar_delay_login()

        ultimo_login_previo = usuario.ultimo_login_en
        usuario.ultimo_login_en = datetime.utcnow()
        usuario.ultimo_login_ip = request.client.host if request.client else None
        db.commit()
        db.refresh(usuario)

        request.session["auth"] = True
        request.session["user"] = usuario.username
        request.session["user_id"] = usuario.id
        request.session["rol"] = usuario.rol or "comun"
        request.session["bootstrap_admin"] = False
        request.session["must_change_password"] = bool(usuario.debe_cambiar_password)
        request.session["ultimo_login_previo"] = (
            ultimo_login_previo.strftime("%Y-%m-%d %H:%M")
            if ultimo_login_previo else ""
        )

        destino = "/mi-perfil?forzar_password=1" if usuario.debe_cambiar_password else "/"
        return RedirectResponse(url=destino, status_code=303)

    aplicar_delay_login()

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
    estado_caso: str = "",
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

    if estado_caso:
        query = query.filter(Procedimiento.estado_caso == estado_caso)

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
            "estado_caso": estado_caso,
        }
    )


@app.get("/health")
def health_check():
    return {"status": "online", "service": "NeuroPACS"}
