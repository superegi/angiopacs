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

@router.get("/usuarios")
def listar_usuarios(
    request: Request,
    db: Session = Depends(get_db)
):
    if request.session.get("rol") != "admin":
        return RedirectResponse(url="/", status_code=303)

    usuarios = db.query(Usuario).order_by(Usuario.id.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="usuarios.html",
        context={
            "usuarios": usuarios
        }
    )
    usuarios = db.query(Usuario).order_by(Usuario.id.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="usuarios.html",
        context={
            "usuarios": usuarios
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
    if request.session.get("rol") != "admin":
        return RedirectResponse(url="/", status_code=303)

    password = password.strip()

    if len(password) > 128:
        password = password[:128]

    password_hash = pwd_context.hash(password)

    nuevo = Usuario(
        username=username,
        password_hash=password_hash,
        nombre=nombre,
        pais=pais,
        ciudad=ciudad,
        edad=int(edad) if edad and edad.isdigit() else None,
        mail=mail,
        especialidad=especialidad,
        rol=rol,
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
    if request.session.get("rol") != "admin":
        return RedirectResponse(url="/", status_code=303)

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()

    if usuario:
        usuario.activo = "no" if usuario.activo == "si" else "si"
        db.commit()

    return RedirectResponse(url="/usuarios", status_code=303)