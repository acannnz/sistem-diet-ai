import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

AI_BASE_URL = os.getenv("AI_BASE_URL", "").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_VISION_MODEL = os.getenv("AI_VISION_MODEL", "")
AI_CHAT_MODEL = os.getenv("AI_CHAT_MODEL", AI_VISION_MODEL)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-ganti-ini")
# true di server (HTTPS) supaya cookie login hanya dikirim lewat koneksi aman
HTTPS_ONLY = os.getenv("HTTPS_ONLY", "false").lower() == "true"
TIMEZONE = ZoneInfo(os.getenv("TIMEZONE", "Asia/Makassar"))

DB_PATH = BASE_DIR / os.getenv("DB_PATH", "data/diet.db")
STATIC_DIR = BASE_DIR / "static"


def parse_users(raw: str) -> dict[str, str]:
    users = {}
    for part in raw.split(","):
        if ":" in part:
            name, pin = part.split(":", 1)
            users[name.strip().lower()] = pin.strip()
    return users


USERS = parse_users(os.getenv("USERS", ""))
