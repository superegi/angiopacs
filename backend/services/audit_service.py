from pathlib import Path
from datetime import datetime, timezone
import os
import uuid
from urllib.parse import unquote

DATA_PATH = Path(os.getenv("DATA_PATH", "/app/data"))

GLOBAL_LOG_DIR = DATA_PATH / "logs"
CASE_LOG_DIR = DATA_PATH / "case_logs"


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _safe(value):
    if value is None:
        return ""
    return str(value).replace("\n", " ").replace("\r", " ").strip()


def _decode_client_value(value):
    if value is None:
        return ""

    try:
        return unquote(str(value)).strip()
    except Exception:
        return str(value).strip()


def _peso_humano(size_bytes):
    try:
        n = int(size_bytes or 0)
    except Exception:
        n = 0

    if n >= 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024 * 1024):.1f} GB"
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} bytes"


def get_actor(request=None):
    if request is None:
        return "sistema"

    try:
        user = request.session.get("user")
        if user:
            return str(user)
    except Exception:
        pass

    return "anonimo"


def get_ip(request=None):
    if request is None:
        return ""

    try:
        if request.client:
            return request.client.host or ""
    except Exception:
        pass

    return ""


def get_user_agent(request=None):
    if request is None:
        return ""

    try:
        return request.headers.get("user-agent", "")
    except Exception:
        return ""


def get_dispositivo(request=None):
    ua = get_user_agent(request).lower()

    if not ua:
        return "desconocido"

    if "iphone" in ua or "android" in ua or "mobile" in ua:
        return "celular"

    if "ipad" in ua or "tablet" in ua:
        return "tablet"

    if "curl" in ua or "httpie" in ua or "python" in ua:
        return "api"

    return "PC"


def get_client_timezone(request=None):
    if request is None:
        return ""

    # 1) AJAX/fetch: header
    try:
        value = request.headers.get("x-client-timezone", "")
        if value:
            return _decode_client_value(value)
    except Exception:
        pass

    # 2) Formularios clásicos: query param opcional
    try:
        value = request.query_params.get("client_timezone", "")
        if value:
            return _decode_client_value(value)
    except Exception:
        pass

    # 3) Fallback principal para formularios clásicos: cookie del navegador
    try:
        value = request.cookies.get("client_timezone", "")
        if value:
            return _decode_client_value(value)
    except Exception:
        pass

    return ""


def get_client_utc_offset_minutes(request=None):
    if request is None:
        return None

    candidates = []

    try:
        candidates.append(request.headers.get("x-client-utc-offset-minutes", ""))
    except Exception:
        pass

    try:
        candidates.append(request.query_params.get("client_utc_offset_minutes", ""))
    except Exception:
        pass

    try:
        candidates.append(request.cookies.get("client_utc_offset_minutes", ""))
    except Exception:
        pass

    for raw in candidates:
        try:
            if raw not in [None, ""]:
                return int(raw)
        except Exception:
            continue

    return None


def _write_line(path: Path, line: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def _persist_db_event(
    db=None,
    action="",
    actor="",
    ip="",
    dispositivo="",
    user_agent="",
    client_timezone="",
    client_utc_offset_minutes=None,
    case_id=None,
    task_id="",
    task_name="",
    status="",
    detail="",
    archivo_nombre=None,
    archivo_bytes=None,
):
    """
    Persiste auditoría en PostgreSQL cuando se entrega db.
    Si falla, no bloquea el flujo principal ni el log TXT.
    """
    if db is None:
        return

    try:
        from models import AuditoriaEvento

        evento = AuditoriaEvento(
            usuario=_safe(actor) or None,
            ip=_safe(ip) or None,
            dispositivo=_safe(dispositivo) or None,
            user_agent=_safe(user_agent) or None,
            client_timezone=_safe(client_timezone) or None,
            client_utc_offset_minutes=client_utc_offset_minutes,
            accion=_safe(action),
            tarea_id=_safe(task_id) or None,
            tarea=_safe(task_name) or None,
            estado=_safe(status) or None,
            caso_id=case_id,
            archivo_nombre=_safe(archivo_nombre) or None,
            archivo_bytes=archivo_bytes,
            detalle=_safe(detail) or None,
        )

        db.add(evento)
        db.flush()

    except Exception:
        pass


def format_line(
    action,
    actor,
    ip="",
    dispositivo="",
    client_timezone="",
    client_utc_offset_minutes=None,
    case_id=None,
    task_id="",
    task_name="",
    status="",
    detail="",
    archivo_nombre=None,
    archivo_bytes=None,
):
    extra_archivo = ""

    if archivo_nombre:
        extra_archivo = (
            f" | archivo={_safe(archivo_nombre)}"
            f" | bytes={_safe(archivo_bytes)}"
            f" | peso={_peso_humano(archivo_bytes)}"
        )

    return (
        f"{now_utc()} | "
        f"usuario={_safe(actor)} | "
        f"ip={_safe(ip)} | "
        f"dispositivo={_safe(dispositivo)} | "
        f"client_timezone={_safe(client_timezone)} | "
        f"client_utc_offset_minutes={_safe(client_utc_offset_minutes)} | "
        f"accion={_safe(action)} | "
        f"tarea_id={_safe(task_id)} | "
        f"tarea={_safe(task_name)} | "
        f"caso={_safe(case_id)} | "
        f"estado={_safe(status)}"
        f"{extra_archivo} | "
        f"detalle={_safe(detail)}\n"
    )


def log_global(
    action,
    actor=None,
    detalle="",
    request=None,
    case_id=None,
    task_id="",
    task_name="",
    status="",
    db=None,
    archivo_nombre=None,
    archivo_bytes=None,
):
    actor = actor or get_actor(request)
    ip = get_ip(request)
    dispositivo = get_dispositivo(request)
    user_agent = get_user_agent(request)
    client_timezone = get_client_timezone(request)
    client_utc_offset_minutes = get_client_utc_offset_minutes(request)

    line = format_line(
        action=action,
        actor=actor,
        ip=ip,
        dispositivo=dispositivo,
        client_timezone=client_timezone,
        client_utc_offset_minutes=client_utc_offset_minutes,
        case_id=case_id,
        task_id=task_id,
        task_name=task_name,
        status=status,
        detail=detalle,
        archivo_nombre=archivo_nombre,
        archivo_bytes=archivo_bytes,
    )

    _write_line(GLOBAL_LOG_DIR / "system_audit.log", line)

    _persist_db_event(
        db=db,
        action=action,
        actor=actor,
        ip=ip,
        dispositivo=dispositivo,
        user_agent=user_agent,
        client_timezone=client_timezone,
        client_utc_offset_minutes=client_utc_offset_minutes,
        case_id=case_id,
        task_id=task_id,
        task_name=task_name,
        status=status,
        detail=detalle,
        archivo_nombre=archivo_nombre,
        archivo_bytes=archivo_bytes,
    )


def log_case(
    case_id,
    action,
    actor=None,
    detalle="",
    request=None,
    task_id="",
    task_name="",
    status="",
    db=None,
    archivo_nombre=None,
    archivo_bytes=None,
):
    if not case_id:
        return

    actor = actor or get_actor(request)
    ip = get_ip(request)
    dispositivo = get_dispositivo(request)
    client_timezone = get_client_timezone(request)
    client_utc_offset_minutes = get_client_utc_offset_minutes(request)

    line = format_line(
        action=action,
        actor=actor,
        ip=ip,
        dispositivo=dispositivo,
        client_timezone=client_timezone,
        client_utc_offset_minutes=client_utc_offset_minutes,
        case_id=case_id,
        task_id=task_id,
        task_name=task_name,
        status=status,
        detail=detalle,
        archivo_nombre=archivo_nombre,
        archivo_bytes=archivo_bytes,
    )

    _write_line(CASE_LOG_DIR / f"case_{case_id}.txt", line)

    log_global(
        action=action,
        actor=actor,
        detalle=detalle,
        request=request,
        case_id=case_id,
        task_id=task_id,
        task_name=task_name,
        status=status,
        db=db,
        archivo_nombre=archivo_nombre,
        archivo_bytes=archivo_bytes,
    )


def start_task(task_name, request=None, case_id=None, detalle="", db=None):
    task_id = uuid.uuid4().hex[:12]

    if case_id:
        log_case(
            case_id=case_id,
            action="TASK_STARTED",
            request=request,
            task_id=task_id,
            task_name=task_name,
            status="started",
            detalle=detalle,
            db=db,
        )
    else:
        log_global(
            action="TASK_STARTED",
            request=request,
            task_id=task_id,
            task_name=task_name,
            status="started",
            detalle=detalle,
            db=db,
        )

    return task_id


def finish_task(task_id, task_name, request=None, case_id=None, status="ok", detalle="", db=None):
    if case_id:
        log_case(
            case_id=case_id,
            action="TASK_FINISHED",
            request=request,
            task_id=task_id,
            task_name=task_name,
            status=status,
            detalle=detalle,
            db=db,
        )
    else:
        log_global(
            action="TASK_FINISHED",
            request=request,
            task_id=task_id,
            task_name=task_name,
            status=status,
            detalle=detalle,
            db=db,
        )


def log_upload_file(case_id, filename, size_bytes, request=None, task_id="", status="ok", detalle="", db=None):
    detail = (
        f"archivo={_safe(filename)}; "
        f"bytes={_safe(size_bytes)}; "
        f"peso={_peso_humano(size_bytes)}; "
        f"{_safe(detalle)}"
    )

    log_case(
        case_id=case_id,
        action="UPLOAD_FILE",
        request=request,
        task_id=task_id,
        task_name="subir_archivos",
        status=status,
        detalle=detail,
        db=db,
        archivo_nombre=filename,
        archivo_bytes=size_bytes,
    )


def log_zip_summary(
    case_id,
    filename,
    size_bytes,
    extracted_count,
    extracted_bytes,
    request=None,
    task_id="",
    status="ok",
    detalle="",
    db=None,
):
    detail = (
        f"zip={_safe(filename)}; "
        f"zip_bytes={_safe(size_bytes)}; "
        f"zip_peso={_peso_humano(size_bytes)}; "
        f"archivos_internos={_safe(extracted_count)}; "
        f"bytes_internos={_safe(extracted_bytes)}; "
        f"peso_interno={_peso_humano(extracted_bytes)}; "
        f"{_safe(detalle)}"
    )

    log_case(
        case_id=case_id,
        action="ZIP_UPLOAD_SUMMARY",
        request=request,
        task_id=task_id,
        task_name="subir_archivos",
        status=status,
        detalle=detail,
        db=db,
        archivo_nombre=filename,
        archivo_bytes=size_bytes,
    )
