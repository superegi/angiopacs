import httpx
import logging
from config import TELEGRAM_API_URL

logger = logging.getLogger(__name__)

async def enviar_mensaje(chat_id: int, texto: str):
    """Envía un mensaje de texto de vuelta al usuario en Telegram."""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": texto}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            return response.json()
        except Exception as e:
            logger.error(f"Error al enviar mensaje a Telegram: {str(e)}")
            return None

async def descargar_foto(file_id: str) -> bytes:
    """Obtiene la ruta de la foto desde Telegram y descarga sus bytes."""
    async with httpx.AsyncClient() as client:
        # 1. Pedir la ruta del archivo a Telegram
        info_url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
        info_res = await client.get(info_url)
        if info_res.status_code != 200:
            return b""
            
        file_path = info_res.json().get("result", {}).get("file_path")
        if not file_path:
            return b""
            
        # 2. Descargar el archivo binario real
        download_url = f"https://api.telegram.org/file/bot{TELEGRAM_API_URL.split('/bot')[-1]}/{file_path}"
        file_res = await client.get(download_url)
        return file_res.content if file_res.status_code == 200 else b""