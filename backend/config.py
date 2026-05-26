import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ESTA ES LA LÍNEA QUE ARREGLA TU PROBLEMA:
DATA_PATH = os.getenv("DATA_PATH", "/app/data")