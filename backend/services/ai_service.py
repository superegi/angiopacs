import io
from PIL import Image

async def extraer_datos_de_imagen(file_bytes: bytes) -> dict | None:
    try:
        image = Image.open(io.BytesIO(file_bytes))
        ancho, alto = image.size

        return {
            "paciente_nombre": "Paciente de prueba",
            "dni": "SIN_DNI",
            "procedimiento": "Procedimiento angiográfico/intervencional",
            "diagnostico": "Pendiente de completar",
            "operadores": "Pendiente",
            "materiales": f"Imagen recibida correctamente ({ancho}x{alto}px). Materiales pendientes de OCR/IA.",
            "ruta_fotos": None,
            "dicom_orthanc_id": None,
        }

    except Exception as e:
        print(f"Error en procesamiento IA: {str(e)}")
        return None
