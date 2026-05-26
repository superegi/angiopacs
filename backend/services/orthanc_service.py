import httpx
import logging

logger = logging.getLogger(__name__)
ORTHANC_URL = "http://orthanc-pacs:8042" # Nombre del contenedor en Docker

async def registrar_datos_en_orthanc(datos: dict):
    """Envía la metadata extraída por IA a Orthanc."""
    try:
        async with httpx.AsyncClient() as client:
            # Ejemplo: Post a Orthanc (ajustar según tu endpoint específico)
            response = await client.post(f"{ORTHANC_URL}/tools/execute-script", json=datos)
            logger.info(f"Orthanc respondió: {response.status_code}")
            return response.status_code == 200
    except Exception as e:
        logger.error(f"Error conectando con Orthanc: {str(e)}")
        return False