import os
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.background import BackgroundTask

router = APIRouter()

ORTHANC_URL = os.getenv("ORTHANC_URL", "http://orthanc-pacs:8042").rstrip("/")
ORTHANC_USER = os.getenv("ORTHANC_USER", os.getenv("ORTHANC_BACKEND_USER", ""))
ORTHANC_PASSWORD = os.getenv("ORTHANC_PASSWORD", os.getenv("ORTHANC_BACKEND_PASSWORD", ""))

ORTHANC_GATEWAY_ENABLED = os.getenv("ORTHANC_GATEWAY_ENABLED", "true").lower() == "true"
ORTHANC_GATEWAY_READ_ONLY = os.getenv("ORTHANC_GATEWAY_READ_ONLY", "true").lower() == "true"

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
}


def usuario_logueado(request: Request) -> bool:
    posibles_llaves = [
        "auth",
        "user_id",
        "usuario_id",
        "username",
        "usuario",
        "logged_in",
        "is_authenticated",
    ]

    if any(request.session.get(k) for k in posibles_llaves):
        return True

    user = request.session.get("user")
    if user:
        return True

    return False


def usuario_admin(request: Request) -> bool:
    if request.session.get("is_admin") is True:
        return True

    for key in ("rol", "role", "tipo_usuario"):
        value = request.session.get(key)
        if isinstance(value, str) and value.lower() == "admin":
            return True

    user = request.session.get("user")
    if isinstance(user, dict):
        role = user.get("rol") or user.get("role") or user.get("tipo_usuario")
        if isinstance(role, str) and role.lower() == "admin":
            return True
        if user.get("is_admin") is True:
            return True

    return False


def limpiar_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in HOP_BY_HOP_HEADERS
    }


def auth_orthanc() -> Optional[tuple[str, str]]:
    if ORTHANC_USER and ORTHANC_PASSWORD:
        return ORTHANC_USER, ORTHANC_PASSWORD
    return None


def reescribir_location(location: str) -> str:
    if not location:
        return location

    if location.startswith(ORTHANC_URL):
        return "/orthanc" + location[len(ORTHANC_URL):]

    if location.startswith("/"):
        return "/orthanc" + location

    return location


async def cerrar_cliente(response: httpx.Response, client: httpx.AsyncClient) -> None:
    await response.aclose()
    await client.aclose()


@router.get("/auth/orthanc")
async def auth_orthanc_check(request: Request):
    if not usuario_logueado(request):
        raise HTTPException(status_code=401, detail="No autenticado")

    return {"ok": True}


@router.api_route(
    "/orthanc",
    methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
)
@router.api_route(
    "/orthanc/{path:path}",
    methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
)
async def orthanc_gateway(request: Request, path: str = ""):
    if not ORTHANC_GATEWAY_ENABLED:
        raise HTTPException(status_code=404, detail="Orthanc gateway deshabilitado")

    if not usuario_logueado(request):
        return RedirectResponse(url="/login", status_code=303)

    if ORTHANC_GATEWAY_READ_ONLY and request.method in WRITE_METHODS and not usuario_admin(request):
        raise HTTPException(
            status_code=403,
            detail="Acceso de escritura a Orthanc restringido a administradores",
        )

    target_url = f"{ORTHANC_URL}/{path}".rstrip("/")

    if request.url.query:
        target_url += f"?{request.url.query}"

    request_headers = dict(request.headers)
    for header in ("host", "authorization", "content-length"):
        request_headers.pop(header, None)

    body = await request.body()

    client = httpx.AsyncClient(timeout=120.0, follow_redirects=False)

    try:
        request_to_orthanc = client.build_request(
            method=request.method,
            url=target_url,
            headers=limpiar_headers(request_headers),
            content=body,
        )

        orthanc_response = await client.send(
            request_to_orthanc,
            stream=True,
            auth=auth_orthanc(),
        )

    except httpx.RequestError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con Orthanc interno: {exc}",
        )

    response_headers = limpiar_headers(dict(orthanc_response.headers))

    if "location" in response_headers:
        response_headers["location"] = reescribir_location(response_headers["location"])

    return StreamingResponse(
        orthanc_response.aiter_bytes(),
        status_code=orthanc_response.status_code,
        headers=response_headers,
        media_type=orthanc_response.headers.get("content-type"),
        background=BackgroundTask(cerrar_cliente, orthanc_response, client),
    )
