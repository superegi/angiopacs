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
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, selectinload

from routers.webhook import router as webhook_router
from routers.pacientes import router as pacientes_router
from database import engine, get_db
from db.migrations import aplicar_migraciones_seguras
from models import Base, Procedimiento, ParticipanteProcedimiento, Usuario, AuditoriaEvento
from services.audit_service import get_client_timezone, get_client_utc_offset_minutes

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


def registrar_evento_seguridad(
    db: Session,
    request: Request,
    accion: str,
    usuario: str | None = None,
    tarea: str | None = None,
    estado: str | None = None,
    detalle: str | None = None,
):
    try:
        evento = AuditoriaEvento(
            usuario=usuario or request.session.get("user"),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            client_timezone=get_client_timezone(request),
            client_utc_offset_minutes=get_client_utc_offset_minutes(request),
            accion=accion,
            tarea=tarea,
            estado=estado,
            detalle=detalle,
        )
        db.add(evento)
    except Exception:
        pass


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
        "1er_operador": "1° operador",
        "1°_operador": "1° operador",
        "segundo_operador": "2° operador",
        "2do_operador": "2° operador",
        "2°_operador": "2° operador",
        "tercer_operador": "3° operador",
        "3er_operador": "3° operador",
        "3°_operador": "3° operador",
        "cuarto_operador": "4° operador",
        "4to_operador": "4° operador",
        "4°_operador": "4° operador",
        "fellow": "Fellow",
        "anestesia": "Anestesia",
    }

    return mapa.get(rol_norm, rol or "")



def etiqueta_tipo_procedimiento(valor: str | None) -> str:
    if not valor:
        return ""

    mapa = {
        "angiografia_cerebral": "Angiografía cerebral",
        "angiografia_medular": "Angiografía medular",
        "test_wada": "Test de WADA",
        "test_oclusion_balon": "Test de oclusión con balón",
        "muestreo_senos_petrosos": "Muestreo de senos petrosos",
        "trombectomia_mecanica": "Trombectomía mecánica",
        "angioplastia_stenting_carotideo": "Angioplastia / stenting carotídeo",
        "trombolisis_intraarterial": "Trombólisis intraarterial",
        "coiling_simple": "Coiling simple",
        "coiling_asistido": "Coiling asistido",
        "divertor_flujo": "Divertor de flujo",
        "dispositivo_intrasacular": "Dispositivo intrasacular",
        "embolizacion_mav": "Embolización de MAV",
        "embolizacion_favd": "Embolización de FAVd",
        "malformacion_vena_galeno": "Malformación vena de Galeno",
        "stenting_senos_venosos": "Stenting senos venosos",
        "trombectomia_fibrinolisis_venosa": "Trombectomía / fibrinólisis venosa",
        "embolizacion_tumor": "Embolización tumoral",
        "embolizacion_epistaxis": "Embolización epistaxis",
        "escleroterapia_cabeza_cuello": "Escleroterapia cabeza/cuello",
        "vertebroplastia_cifoplastia": "Vertebroplastia / cifoplastia",
        "infiltracion_bloqueo_raquis": "Infiltración / bloqueo raquídeo",
        "tratamiento_fuga_lcr": "Tratamiento fuga LCR",
        "otro": "Otro",
    }

    return mapa.get(valor, str(valor).replace("_", " ").strip())



# ANGIO-LISTADO-HELPERS-V21
def angio_v21_estado_label(valor: str | None) -> str:
    mapa = {
        "abierto": "Abierto",
        "hospitalizado": "Está hospitalizado",
        "esta_hospitalizado": "Está hospitalizado",
        "pendiente_control_ambulatorio": "Pendiente control ambulatorio",
        "cerrado": "Cerrado",
    }
    return mapa.get(valor or "", valor or "Abierto")


def angio_v21_tipo_procedimiento_label(valor: str | None) -> str:
    if not valor:
        return ""

    mapa = {
        "angiografia_cerebral": "Angiografía cerebral",
        "angiografia_medular": "Angiografía medular",
        "test_wada": "Test de WADA",
        "test_oclusion_balon": "Test de oclusión con balón",
        "muestreo_senos_petrosos": "Muestreo de senos petrosos",
        "trombectomia_mecanica": "Trombectomía mecánica",
        "angioplastia_stenting_carotideo": "Angioplastia / stenting carotídeo",
        "trombolisis_intraarterial": "Trombólisis intraarterial",
        "coiling_simple": "Coiling simple",
        "coiling_asistido": "Coiling asistido",
        "divertor_flujo": "Divertor de flujo",
        "dispositivo_intrasacular": "Dispositivo intrasacular",
        "embolizacion_mav": "Embolización MAV",
        "embolizacion_favd": "Embolización FAVd",
        "malformacion_vena_galeno": "Malformación vena de Galeno",
        "stenting_senos_venosos": "Stenting senos venosos",
        "trombectomia_fibrinolisis_venosa": "Trombectomía / fibrinólisis venosa",
        "embolizacion_tumor": "Embolización tumoral",
        "embolizacion_epistaxis": "Embolización epistaxis",
        "escleroterapia_cabeza_cuello": "Escleroterapia cabeza/cuello",
        "vertebroplastia_cifoplastia": "Vertebroplastia / cifoplastia",
        "infiltracion_bloqueo_raquis": "Infiltración / bloqueo raquídeo",
        "tratamiento_fuga_lcr": "Tratamiento fuga LCR",
        "otro": "Otro",
    }

    return mapa.get(valor, str(valor).replace("_", " ").strip())


def angio_v21_rol_label(valor: str | None) -> str:
    if not valor:
        return "Participante"

    txt = str(valor).strip()
    norm = (
        txt.lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("°", "")
    )

    mapa = {
        "primer_operador": "1er operador",
        "1er_operador": "1er operador",
        "1_operador": "1er operador",
        "segundo_operador": "2do operador",
        "2do_operador": "2do operador",
        "2_operador": "2do operador",
        "tercer_operador": "3er operador",
        "3er_operador": "3er operador",
        "3_operador": "3er operador",
        "cuarto_operador": "4to operador",
        "4to_operador": "4to operador",
        "4_operador": "4to operador",
        "fellow": "Fellow",
        "asistente": "Asistente",
        "anestesia": "Anestesia",
    }

    return mapa.get(norm, txt)


def angio_v21_es_operador(valor: str | None) -> bool:
    if not valor:
        return False

    norm = str(valor).strip().lower().replace(" ", "_").replace("-", "_")
    return "operador" in norm or norm in {"fellow", "asistente", "anestesia"}




# ANGIO-LISTADO-OPERADORES-V22
def angio_v22_estado_label(valor: str | None) -> str:
    mapa = {
        "abierto": "Abierto",
        "hospitalizado": "Está hospitalizado",
        "esta_hospitalizado": "Está hospitalizado",
        "pendiente_control_ambulatorio": "Pendiente control ambulatorio",
        "cerrado": "Cerrado",
    }
    return mapa.get(valor or "", valor or "Abierto")


def angio_v22_tipo_procedimiento_label(valor: str | None) -> str:
    if not valor:
        return ""

    mapa = {
        "angiografia_cerebral": "Angiografía cerebral",
        "angiografia_medular": "Angiografía medular",
        "test_wada": "Test de WADA",
        "test_oclusion_balon": "Test de oclusión con balón",
        "muestreo_senos_petrosos": "Muestreo de senos petrosos",
        "trombectomia_mecanica": "Trombectomía mecánica",
        "angioplastia_stenting_carotideo": "Angioplastia / stenting carotídeo",
        "trombolisis_intraarterial": "Trombólisis intraarterial",
        "coiling_simple": "Coiling simple",
        "coiling_asistido": "Coiling asistido",
        "divertor_flujo": "Divertor de flujo",
        "dispositivo_intrasacular": "Dispositivo intrasacular",
        "embolizacion_mav": "Embolización MAV",
        "embolizacion_favd": "Embolización FAVd",
        "malformacion_vena_galeno": "Malformación vena de Galeno",
        "stenting_senos_venosos": "Stenting senos venosos",
        "trombectomia_fibrinolisis_venosa": "Trombectomía / fibrinólisis venosa",
        "embolizacion_tumor": "Embolización tumoral",
        "embolizacion_epistaxis": "Embolización epistaxis",
        "escleroterapia_cabeza_cuello": "Escleroterapia cabeza/cuello",
        "vertebroplastia_cifoplastia": "Vertebroplastia / cifoplastia",
        "infiltracion_bloqueo_raquis": "Infiltración / bloqueo raquídeo",
        "tratamiento_fuga_lcr": "Tratamiento fuga LCR",
        "otro": "Otro",
    }
    return mapa.get(valor, str(valor).replace("_", " ").strip())


def angio_v22_es_operador(valor: str | None) -> bool:
    if not valor:
        return False

    normalizado = str(valor).strip().lower().replace(" ", "_").replace("-", "_")
    return "operador" in normalizado


def angio_v22_split_paciente(p) -> tuple[str, str, str]:
    nombre = (getattr(p, "paciente_nombre", None) or "").strip()
    apellido = (getattr(p, "paciente_apellido", None) or "").strip()

    if nombre or apellido:
        completo = " ".join(x for x in [apellido, nombre] if x).strip()
        return nombre, apellido, completo

    legacy = (getattr(p, "paciente", None) or "").strip()
    if legacy:
        partes = legacy.split()
        if len(partes) >= 2:
            apellido = partes[-1]
            nombre = " ".join(partes[:-1])
            return nombre, apellido, legacy
        return legacy, "", legacy

    return "", "", "Sin nombre"


def angio_v22_operadores_resumen(p) -> list[str]:
    nombres = []
    vistos = set()

    participantes = list(getattr(p, "participantes", []) or [])
    for participante in participantes:
        rol = getattr(participante, "rol", None)
        nombre = (getattr(participante, "nombre", None) or "").strip()

        if not nombre:
            continue

        # Solo operadores. No fellow puro, no asistente, no anestesia.
        if not angio_v22_es_operador(rol):
            continue

        clave = nombre.lower()
        if clave in vistos:
            continue

        vistos.add(clave)
        nombres.append(nombre)

    # Fallback legacy si no hay participantes estructurados.
    if not nombres:
        for attr in ["primer_operador", "segundo_operador", "tercer_operador", "cuarto_operador"]:
            nombre = (getattr(p, attr, None) or "").strip()
            if nombre and nombre.lower() not in vistos:
                vistos.add(nombre.lower())
                nombres.append(nombre)

    return nombres


def construir_resumen_procedimiento(p: Procedimiento) -> dict:
    paciente_nombre, paciente_apellido, paciente = angio_v22_split_paciente(p)
    operadores_nombres = angio_v22_operadores_resumen(p)

    tiene_archivos = bool(list(getattr(p, "archivos", []) or []))

    return {
        "id": p.id,
        "fecha": getattr(p, "fecha", None),
        "estado_caso": getattr(p, "estado_caso", None) or "abierto",
        "estado_caso_label": angio_v22_estado_label(getattr(p, "estado_caso", None)),
        "paciente": paciente,
        "paciente_nombre": paciente_nombre,
        "paciente_apellido": paciente_apellido,
        "historia_clinica": getattr(p, "historia_clinica", None) or "",
        "institucion": getattr(p, "institucion", None) or "",
        "operadores": [{"nombre": nombre} for nombre in operadores_nombres],
        "operadores_nombres": operadores_nombres,
        "tipo_procedimiento": getattr(p, "tipo_procedimiento", None) or "",
        "tipo_procedimiento_label": angio_v22_tipo_procedimiento_label(getattr(p, "tipo_procedimiento", None)),
        "procedimiento": getattr(p, "procedimiento", None) or "",
        "diagnostico": getattr(p, "diagnostico", None) or "",
        "tiene_archivos": tiene_archivos,
    }



@app.get("/casos-activos")
def casos_activos(
    request: Request,
    db: Session = Depends(get_db)
):
    auth = require_login(request)
    if auth:
        return auth

    estados_visibles = ["abierto", "hospitalizado", "pendiente_control_ambulatorio"]

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
        "pendiente_control_ambulatorio": 0,
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

        registrar_evento_seguridad(
            db=db,
            request=request,
            accion="LOGIN_OK",
            usuario=usuario.username,
            tarea="login",
            estado="ok",
            detalle="Login exitoso.",
        )

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

    registrar_evento_seguridad(
        db=db,
        request=request,
        accion="LOGIN_FAILED",
        usuario=username,
        tarea="login",
        estado="error",
        detalle="Usuario o contraseña incorrectos.",
    )
    db.commit()

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Usuario o contraseña incorrectos"}
    )


@app.get("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
):
    usuario = request.session.get("user")
    registrar_evento_seguridad(
        db=db,
        request=request,
        accion="LOGOUT",
        usuario=usuario,
        tarea="logout",
        estado="ok",
        detalle="Cierre de sesión.",
    )
    db.commit()

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
    ordenar: str = "id",
    direccion: str = "desc",
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
                Procedimiento.tipo_procedimiento.ilike(filtro_buscar),
                Procedimiento.primer_operador.ilike(filtro_buscar),
                Procedimiento.segundo_operador.ilike(filtro_buscar),
                Procedimiento.fellow.ilike(filtro_buscar),
                Procedimiento.operadores.ilike(filtro_buscar),
                Procedimiento.participantes.any(ParticipanteProcedimiento.nombre.ilike(filtro_buscar)),
                Procedimiento.participantes.any(ParticipanteProcedimiento.rol.ilike(filtro_buscar)),
            )
        )

    direccion = (direccion or "desc").lower()
    if direccion not in ["asc", "desc"]:
        direccion = "desc"

    ordenar = (ordenar or "id").lower()
    if ordenar not in ["id", "fecha", "paciente"]:
        ordenar = "id"

    if ordenar == "fecha":
        columna_orden = Procedimiento.fecha
    elif ordenar == "paciente":
        columna_orden = func.lower(
            func.concat(
                func.coalesce(Procedimiento.paciente_apellido, ""),
                " ",
                func.coalesce(Procedimiento.paciente_nombre, ""),
            )
        )
    else:
        columna_orden = Procedimiento.id

    if direccion == "asc":
        query = query.order_by(columna_orden.asc().nullslast(), Procedimiento.id.asc())
    else:
        query = query.order_by(columna_orden.desc().nullslast(), Procedimiento.id.desc())

    procedimientos_db = query.all()
    procedimientos = [
        construir_resumen_procedimiento(p)
        for p in procedimientos_db
    ]

    filtros_activos = {
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "operador": operador,
        "lugar": lugar,
        "buscar": buscar,
        "estado_caso": estado_caso,
    }

    filtros_activos = {
        k: v for k, v in filtros_activos.items()
        if v not in [None, ""]
    }

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
            "ordenar": ordenar,
            "direccion": direccion,
            "filtros_activos": filtros_activos,
        }
    )


@app.get("/health")
def health_check():
    return {"status": "online", "service": "NeuroPACS"}
