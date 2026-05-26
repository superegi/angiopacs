# services/webhook.py
from services.ai_service import analizar_imagen_pacs
from services.orthanc_service import registrar_datos_en_orthanc
from services.telegram_service import enviar_mensaje
import logging

logger = logging.getLogger(__name__)

async def telegram_webhook_logic(request):
    try:
        data = await request.json()
        logger.info(f"Webhook recibido: {data}")
        
        # Obtenemos chat_id de forma segura
        chat_id = data.get("message", {}).get("chat", {}).get("id")
        
        if not chat_id:
            return {"status": "error", "message": "No se encontró chat_id"}

        # 1. Analizar con IA (simulado)
        resultado_ia = await analizar_imagen_pacs(file_bytes=b"datos_de_prueba")
        
        # 2. Registrar en Orthanc
        exito = await registrar_datos_en_orthanc(resultado_ia)
        
        # 3. Responder al usuario
        mensaje = "¡Registro exitoso en AngioPACS!" if exito else "Error al guardar en Orthanc"
        await enviar_mensaje(chat_id, mensaje)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error procesando webhook: {str(e)}")
        return {"status": "error", "message": str(e)}