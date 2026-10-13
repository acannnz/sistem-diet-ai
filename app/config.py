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
# Mode "berpikir" model untuk chat & pemilihan TKPI: none | low | medium | high, kosongkan = default model.
# "none" membuat jawaban jauh lebih cepat (coach tidak butuh penalaran panjang).
AI_CHAT_REASONING = os.getenv("AI_CHAT_REASONING", "none").strip()

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

# Akun demo (mis. untuk portofolio): dipisah dari akun asli, kuota AI harian, data direset tiap hari
DEMO_USERS = {u.strip().lower() for u in os.getenv("DEMO_USERS", "demo").split(",") if u.strip()}
DEMO_DAILY_AI_LIMIT = int(os.getenv("DEMO_DAILY_AI_LIMIT", "30"))
