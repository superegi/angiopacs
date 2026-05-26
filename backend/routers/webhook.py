from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from database import get_db
import crud
import logging

from services.file_service import guardar_imagen
from services.telegram_service import enviar_mensaje, descargar_foto

router = APIRouter()
logger = logging.getLogger(__name__)

def extraer_texto_simple(message: dict) -> str:
    return (message.get("text") or message.get("caption") or "").strip()

@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        content_type = request.headers.get("content-type", "")

        if "application/json" not in content_type:
            file_bytes = await request.body()
            if not file_bytes:
                raise HTTPException(status_code=400, detail="No se recibió archivo")

            ruta = guardar_imagen(file_bytes)
            archivo = crud.crear_archivo(
                db=db,
                ruta=ruta,
                tipo="foto",
                origen="webhook_directo",
                estado="pendiente"
            )
            return {"status": "ok", "archivo_id": archivo.id, "ruta": ruta}

        update = await request.json()
        message = update.get("message") or update.get("edited_message")

        if not message:
            return {"status": "ignored", "reason": "sin message"}

        chat_id = str(message.get("chat", {}).get("id"))
        texto = extraer_texto_simple(message)

        if not chat_id:
            return {"status": "ignored", "reason": "sin chat_id"}

        # COMANDO: /estado
        if texto.startswith("/estado"):
            sesion = crud.obtener_sesion_activa(db, chat_id)
            if not sesion:
                await enviar_mensaje(chat_id, "No hay caso activo.")
                return {"status": "ok"}

            proc = crud.obtener_procedimiento(db, sesion.procedimiento_id)
            await enviar_mensaje(
                chat_id,
                f"Caso activo:\nID: {proc.id}\nPaciente: {proc.paciente_nombre or 'Sin nombre'}\nHC: {proc.historia_clinica or 'Sin HC'}"
            )
            return {"status": "ok"}

        # COMANDO: /fin
        if texto.startswith("/fin"):
            crud.cerrar_sesiones_activas(db, chat_id)
            await enviar_mensaje(chat_id, "Sesión de carga cerrada.")
            return {"status": "ok"}

        # COMANDO: /usar ID
        if texto.startswith("/usar"):
            partes = texto.split()
            if len(partes) < 2 or not partes[1].isdigit():
                await enviar_mensaje(chat_id, "Uso correcto: /usar 3")
                return {"status": "ok"}

            procedimiento_id = int(partes[1])
            proc = crud.obtener_procedimiento(db, procedimiento_id)

            if not proc:
                await enviar_mensaje(chat_id, f"No existe procedimiento ID {procedimiento_id}.")
                return {"status": "ok"}

            crud.crear_sesion_carga(db, chat_id, procedimiento_id)

            await enviar_mensaje(
                chat_id,
                f"Caso activo seleccionado:\nID: {proc.id}\nPaciente: {proc.paciente_nombre or 'Sin nombre'}\nHC: {proc.historia_clinica or 'Sin HC'}\n\nAhora envía fotos/materiales. Para cerrar: /fin"
            )
            return {"status": "ok"}

        # COMANDO: /nuevo Nombre | HC
        if texto.startswith("/nuevo"):
            contenido = texto.replace("/nuevo", "", 1).strip()

            paciente_nombre = None
            historia_clinica = None

            if "|" in contenido:
                paciente_nombre, historia_clinica = [x.strip() for x in contenido.split("|", 1)]
            elif contenido:
                paciente_nombre = contenido

            proc = crud.crear_procedimiento_basico(db, paciente_nombre, historia_clinica)
            crud.crear_sesion_carga(db, chat_id, proc.id)

            await enviar_mensaje(
                chat_id,
                f"Nuevo caso creado y activado.\nID: {proc.id}\nPaciente: {proc.paciente_nombre or 'Sin nombre'}\nHC: {proc.historia_clinica or 'Sin HC'}\n\nEnvía fotos/materiales. Para cerrar: /fin"
            )
            return {"status": "ok"}

        # COMANDO: /ultimos
        if texto.startswith("/ultimos"):
            procedimientos = crud.listar_ultimos_procedimientos(db, 5)

            if not procedimientos:
                await enviar_mensaje(chat_id, "No hay procedimientos creados.")
                return {"status": "ok"}

            lineas = ["Últimos casos:"]
            for p in procedimientos:
                lineas.append(
                    f"{p.id}) {p.paciente_nombre or 'Sin nombre'} | HC: {p.historia_clinica or 'Sin HC'}"
                )
            lineas.append("\nUsa: /usar ID")
            await enviar_mensaje(chat_id, "\n".join(lineas))
            return {"status": "ok"}

        # RECEPCIÓN DE FOTO
        fotos = message.get("photo", [])
        if fotos:
            sesion = crud.obtener_sesion_activa(db, chat_id)

            if not sesion:
                await enviar_mensaje(
                    chat_id,
                    "Recibí una foto, pero no hay caso activo.\n\nOpciones:\n/nuevo Nombre Paciente | Historia clínica\n/ultimos\n/usar ID"
                )
                return {"status": "ok", "reason": "foto sin sesion activa"}

            file_id = fotos[-1]["file_id"]
            file_bytes = await descargar_foto(file_id)

            if not file_bytes:
                await enviar_mensaje(chat_id, "No pude descargar la foto desde Telegram.")
                return {"status": "error", "reason": "no descarga"}

            ruta = guardar_imagen(file_bytes)

            archivo = crud.crear_archivo(
                db=db,
                ruta=ruta,
                tipo="foto",
                origen="telegram",
                procedimiento_id=sesion.procedimiento_id,
                telegram_file_id=file_id,
                telegram_chat_id=chat_id,
                estado="asociado"
            )

            proc = crud.obtener_procedimiento(db, sesion.procedimiento_id)

            await enviar_mensaje(
                chat_id,
                f"Foto guardada y asociada.\nArchivo ID: {archivo.id}\nCaso: {proc.paciente_nombre or 'Sin nombre'} | HC: {proc.historia_clinica or 'Sin HC'}"
            )
            return {"status": "ok", "archivo_id": archivo.id}

        # MENSAJE SIN FOTO
        await enviar_mensaje(
            chat_id,
            "Comandos disponibles:\n/nuevo Nombre Paciente | Historia clínica\n/ultimos\n/usar ID\n/estado\n/fin"
        )
        return {"status": "ok", "reason": "mensaje informativo"}

    except Exception as e:
        logger.error(f"Error en webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
