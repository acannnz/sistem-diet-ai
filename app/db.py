import re
import sqlite3
from contextlib import contextmanager
from difflib import SequenceMatcher

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    sex TEXT DEFAULT 'L',            -- 'L' laki-laki, 'P' perempuan
    birth_year INTEGER,
    height_cm REAL,
    weight_kg REAL,
    activity TEXT DEFAULT 'ringan',  -- minim | ringan | sedang | berat
    goal TEXT DEFAULT 'turun',       -- turun | jaga | naik
    target_kcal INTEGER              -- isi untuk menimpa hasil hitungan otomatis
);

-- Nilai gizi per 100 gram (diisi dari import_gizi.py)
CREATE TABLE IF NOT EXISTS foods (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kcal REAL DEFAULT 0,
    protein REAL DEFAULT 0,
    fat REAL DEFAULT 0,
    carb REAL DEFAULT 0,
    fiber REAL DEFAULT 0,
    portion_g REAL,                  -- berat 1 porsi standar (opsional)
    portion_label TEXT               -- mis. "1 piring", "1 potong sedang"
);
CREATE INDEX IF NOT EXISTS idx_foods_name ON foods(name);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    date TEXT NOT NULL,              -- YYYY-MM-DD
    time TEXT NOT NULL,              -- HH:MM
    meal TEXT NOT NULL,              -- sarapan | siang | malam | camilan
    food_id INTEGER REFERENCES foods(id),
    name TEXT NOT NULL,
    grams REAL NOT NULL,
    kcal REAL NOT NULL,
    protein REAL NOT NULL,
    fat REAL NOT NULL,
    carb REAL NOT NULL,
    source TEXT DEFAULT 'db'         -- db = dari data ahli gizi, ai = perkiraan AI
);
CREATE INDEX IF NOT EXISTS idx_logs_user_date ON logs(user_id, date);

CREATE TABLE IF NOT EXISTS weights (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    date TEXT NOT NULL,
    weight_kg REAL NOT NULL,
    UNIQUE(user_id, date)
);
"""


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)


# ---------- Target kalori ----------

ACTIVITY_FACTOR = {"minim": 1.2, "ringan": 1.375, "sedang": 1.55, "berat": 1.725}


def compute_targets(user: dict, age: int | None) -> dict | None:
    """Mifflin-St Jeor -> TDEE -> target kalori & makro."""
    w, h = user.get("weight_kg"), user.get("height_cm")
    if not (w and h and age):
        return None
    bmr = 10 * w + 6.25 * h - 5 * age + (5 if user.get("sex") == "L" else -161)
    tdee = bmr * ACTIVITY_FACTOR.get(user.get("activity") or "ringan", 1.375)
    goal = user.get("goal") or "turun"
    kcal = tdee + {"turun": -500, "jaga": 0, "naik": 300}.get(goal, 0)
    kcal = max(kcal, 1500 if user.get("sex") == "L" else 1200)
    if user.get("target_kcal"):
        kcal = user["target_kcal"]
    protein = w * (1.6 if goal == "turun" else 1.2)
    fat = kcal * 0.25 / 9
    carb = max(kcal - protein * 4 - fat * 9, 0) / 4
    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "kcal": round(kcal),
        "protein": round(protein),
        "fat": round(fat),
        "carb": round(carb),
    }


# ---------- Pencarian makanan ----------

def _tokens(s: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).split()


def search_foods(db: sqlite3.Connection, query: str, limit: int = 8) -> list[dict]:
    """Cari makanan: kandidat dari LIKE per kata, lalu diurutkan dengan skor kemiripan."""
    tokens = _tokens(query)
    if not tokens:
        return []
    where = " OR ".join("lower(name) LIKE ?" for _ in tokens)
    rows = db.execute(
        f"SELECT * FROM foods WHERE {where} LIMIT 500", [f"%{t}%" for t in tokens]
    ).fetchall()
    q = " ".join(tokens)

    def score(row):
        name_tokens = _tokens(row["name"])
        # cocok per kata (awalan), supaya "ayam" tidak cocok dengan "bayam"
        hits = sum(1 for t in tokens if any(n.startswith(t) or (len(n) >= 3 and t.startswith(n)) for n in name_tokens))
        if not hits:
            return 0
        ratio = SequenceMatcher(None, q, " ".join(name_tokens)).ratio()
        # utamakan yang memuat semua kata pencarian, lalu yang kata tambahannya sedikit
        return 0.6 * hits / len(tokens) + 0.25 * hits / len(name_tokens) + 0.15 * ratio

    scored = [(score(r), r) for r in rows]
    ranked = sorted((x for x in scored if x[0] > 0), key=lambda x: x[0], reverse=True)[:limit]
    return [dict(r) | {"score": round(s, 2)} for s, r in ranked]


def nutrients_for(food: dict, grams: float) -> dict:
    f = grams / 100
    return {k: round((food.get(k) or 0) * f, 1) for k in ("kcal", "protein", "fat", "carb")}
