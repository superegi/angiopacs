from datetime import datetime

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from database import get_db
from models import Usuario

router = APIRouter()

templates = Jinja2Templates(directory="templates")

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)


def es_admin(request: Request) -> bool:
    return request.session.get("rol") == "admin"


def require_login(request: Request):
    if request.session.get("auth") is not True:
        return RedirectResponse(url="/login", status_code=303)
    return None


def get_usuario_actual(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(Usuario).filter(Usuario.id == user_id).first()


def bool_usuario(valor) -> bool:
    if valor is True:
        return True
    texto = str(valor or "").strip().lower()
    return texto in ["si", "sí", "true", "1", "activo", "active"]


def edad_int(valor: str | None):
    valor = (valor or "").strip()
    if not valor:
        return None
    return int(valor) if valor.isdigit() else None


@router.get("/usuarios")
def listar_usuarios(
    request: Request,
    db: Session = Depends(get_db)
):
    if not es_admin(request):
        return RedirectResponse(url="/", status_code=303)

    usuarios = db.query(Usuario).order_by(Usuario.id.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="usuarios.html",
        context={
            "usuarios": usuarios,
            "error": None,
        }
    )


@router.post("/usuarios/nuevo")
def nuevo_usuario(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    nombre: str = Form(None),
    pais: str = Form(None),
    ciudad: str = Form(None),
    edad: str = Form(None),
    mail: str = Form(None),
    especialidad: str = Form(None),
    rol: str = Form("comun"),
    db: Session = Depends(get_db)
):
    if not es_admin(request):
        return RedirectResponse(url="/", status_code=303)

    username = (username or "").strip()
    password = (password or "").strip()

    if not username or not password:
        usuarios = db.query(Usuario).order_by(Usuario.id.desc()).all()
        return templates.TemplateResponse(
            request=request,
            name="usuarios.html",
            context={
                "usuarios": usuarios,
                "error": "Usuario y contraseña temporal son obligatorios.",
            },
            status_code=400,
        )

    if len(password) > 128:
        password = password[:128]

    existente = db.query(Usuario).filter(Usuario.username == username).first()
    if existente:
        usuarios = db.query(Usuario).order_by(Usuario.id.desc()).all()
        return templates.TemplateResponse(
            request=request,
            name="usuarios.html",
            context={
                "usuarios": usuarios,
                "error": "Ya existe un usuario con ese username.",
            },
            status_code=400,
        )

    nuevo = Usuario(
        username=username,
        password_hash=pwd_context.hash(password),
        nombre=nombre,
        pais=pais,
        ciudad=ciudad,
        edad=edad_int(edad),
        mail=mail,
        especialidad=especialidad,
        rol=rol,
        activo="si",
        debe_cambiar_password=True,
        password_temporal=True,
    )

    db.add(nuevo)
    db.commit()

    return RedirectResponse(
        url="/usuarios",
        status_code=303
    )


@router.post("/usuarios/{usuario_id}/toggle-activo")
def toggle_usuario(
    usuario_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    if not es_admin(request):
        return RedirectResponse(url="/", status_code=303)

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()

    if usuario:
        usuario.activo = "no" if bool_usuario(usuario.activo) else "si"
        db.commit()

    return RedirectResponse(url="/usuarios", status_code=303)


@router.post("/usuarios/{usuario_id}/reset-password")
def reset_password_usuario(
    usuario_id: int,
    request: Request,
    password_temporal: str = Form(...),
    db: Session = Depends(get_db)
):
    if not es_admin(request):
        return RedirectResponse(url="/", status_code=303)

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    password_temporal = (password_temporal or "").strip()

    if usuario and password_temporal:
        if len(password_temporal) > 128:
            password_temporal = password_temporal[:128]

        usuario.password_hash = pwd_context.hash(password_temporal)
        usuario.debe_cambiar_password = True
        usuario.password_temporal = True
        db.commit()

    return RedirectResponse(url="/usuarios", status_code=303)


@router.get("/mi-perfil")
def mi_perfil_get(
    request: Request,
    forzar_password: str = "",
    ok: str = "",
    db: Session = Depends(get_db)
):
    auth = require_login(request)
    if auth:
        return auth

    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/logout", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="mi_perfil.html",
        context={
            "usuario": usuario,
            "forzar_password": bool(forzar_password),
            "ok": bool(ok),
            "error": None,
        }
    )


@router.post("/mi-perfil")
def mi_perfil_post(
    request: Request,
    nombre: str = Form(None),
    pais: str = Form(None),
    ciudad: str = Form(None),
    edad: str = Form(None),
    mail: str = Form(None),
    especialidad: str = Form(None),
    password_actual: str = Form(""),
    password_nueva: str = Form(""),
    password_confirmar: str = Form(""),
    db: Session = Depends(get_db)
):
    auth = require_login(request)
    if auth:
        return auth

    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/logout", status_code=303)

    debe_cambiar = bool(usuario.debe_cambiar_password)
    password_actual = password_actual or ""
    password_nueva = password_nueva or ""
    password_confirmar = password_confirmar or ""

    usuario.nombre = nombre
    usuario.pais = pais
    usuario.ciudad = ciudad
    usuario.edad = edad_int(edad)
    usuario.mail = mail
    usuario.especialidad = especialidad
    usuario.perfil_actualizado_en = datetime.utcnow()

    quiere_cambiar_password = bool(password_nueva or password_confirmar or debe_cambiar)

    if quiere_cambiar_password:
        if len(password_nueva) < 8:
            return templates.TemplateResponse(
                request=request,
                name="mi_perfil.html",
                context={
                    "usuario": usuario,
                    "forzar_password": debe_cambiar,
                    "ok": False,
                    "error": "La nueva contraseña debe tener al menos 8 caracteres.",
                },
                status_code=400,
            )

        if password_nueva != password_confirmar:
            return templates.TemplateResponse(
                request=request,
                name="mi_perfil.html",
                context={
                    "usuario": usuario,
                    "forzar_password": debe_cambiar,
                    "ok": False,
                    "error": "La confirmación de contraseña no coincide.",
                },
                status_code=400,
            )

        if not debe_cambiar:
            try:
                actual_ok = pwd_context.verify(password_actual, usuario.password_hash)
            except Exception:
                actual_ok = False

            if not actual_ok:
                return templates.TemplateResponse(
                    request=request,
                    name="mi_perfil.html",
                    context={
                        "usuario": usuario,
                        "forzar_password": False,
                        "ok": False,
                        "error": "La contraseña actual no es correcta.",
                    },
                    status_code=400,
                )

        usuario.password_hash = pwd_context.hash(password_nueva)
        usuario.debe_cambiar_password = False
        usuario.password_temporal = False
        request.session["must_change_password"] = False

    db.commit()

    return RedirectResponse(url="/mi-perfil?ok=1", status_code=303)
