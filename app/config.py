import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "datos" / "gestor.db"))
APP_TOKEN = os.getenv("APP_TOKEN", "cambia-este-token-secreto")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

WELCOME_TEMPLATE = os.getenv(
    "WELCOME_TEMPLATE",
    "¡Hola {nombre}! 👋 Bienvenido/a al grupo. Por favor completa tus datos aquí: {link}",
)
GOOGLE_FORM_URL = os.getenv("GOOGLE_FORM_URL", "")

CLOUD_API_PHONE_ID = os.getenv("CLOUD_API_PHONE_ID", "")
CLOUD_API_TOKEN = os.getenv("CLOUD_API_TOKEN", "")
CLOUD_API_VERSION = os.getenv("CLOUD_API_VERSION", "v21.0")

DEFAULT_CHANNEL = os.getenv("DEFAULT_CHANNEL", "bot")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
