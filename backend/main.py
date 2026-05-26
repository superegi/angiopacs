from pathlib import Path
import os

from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

from routers.webhook import router as webhook_router
from routers.pacientes import router as pacientes_router
from database import engine, get_db
from models import Base, Procedimiento

from routers.usuarios import router as usuarios_router

Base.metadata.create_all(bind=engine)

BASE_DIR = Path(__file__).resolve().parent

APP_USER = os.getenv("ANGIOPACS_USER", "egidio")
APP_PASSWORD = os.getenv("ANGIOPACS_PASSWORD", "cambia_esta_clave")
SESSION_SECRET = os.getenv("ANGIOPACS_SESSION_SECRET", "cambia_este_secreto_largo")

app = FastAPI(
    title="AngioPACS",
    description="Biblioteca procedural asistida por IA",
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

    query = db.query(Procedimiento)

    if fecha_desde:
        query = query.filter(Procedimiento.fecha >= fecha_desde)

    if fecha_hasta:
        query = query.filter(Procedimiento.fecha <= fecha_hasta)

    if lugar:
        query = query.filter(Procedimiento.lugar.ilike(f"%{lugar}%"))

    if operador:
        filtro_operador = f"%{operador}%"
        query = query.filter(
            (Procedimiento.primer_operador.ilike(filtro_operador)) |
            (Procedimiento.segundo_operador.ilike(filtro_operador)) |
            (Procedimiento.fellow.ilike(filtro_operador)) |
            (Procedimiento.operadores.ilike(filtro_operador))
        )

    if buscar:
        filtro_buscar = f"%{buscar}%"
        query = query.filter(
            (Procedimiento.paciente_nombre.ilike(filtro_buscar)) |
            (Procedimiento.diagnostico.ilike(filtro_buscar)) |
            (Procedimiento.procedimiento.ilike(filtro_buscar)) |
            (Procedimiento.historia_clinica.ilike(filtro_buscar))
        )

    procedimientos = query.order_by(Procedimiento.id.desc()).all()

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
    return {"status": "online", "service": "AngioPACS"}
