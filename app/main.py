import base64
import re
import secrets
import time
from datetime import date as date_cls, datetime, timedelta

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from . import ai
from .config import HTTPS_ONLY, SECRET_KEY, STATIC_DIR, TIMEZONE, USERS
from .db import compute_targets, get_db, init_db, nutrients_for, search_foods

app = FastAPI(title="Diet Scan", docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(
    SessionMiddleware, secret_key=SECRET_KEY, max_age=60 * 60 * 24 * 365, same_site="lax", https_only=HTTPS_ONLY
)
init_db()


@app.exception_handler(ai.AIError)
async def ai_error_handler(_: Request, exc: ai.AIError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


# ---------- Helpers ----------

def now():
    return datetime.now(TIMEZONE)


def today() -> str:
    return now().date().isoformat()


def default_meal(hour: int) -> str:
    if 4 <= hour < 10:
        return "sarapan"
    if 10 <= hour < 15:
        return "siang"
    if 15 <= hour < 18:
        return "camilan"
    return "malam"


def current_user(request: Request) -> dict:
    username = request.session.get("user")
    if not username or username not in USERS:
        raise HTTPException(401, "Belum login")
    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            db.execute("INSERT INTO users (username, display_name) VALUES (?, ?)", (username, username.title()))
            row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row)


def user_payload(user: dict) -> dict:
    age = now().year - user["birth_year"] if user.get("birth_year") else None
    return {"user": user, "age": age, "targets": compute_targets(user, age)}


def day_totals(db, user_id: int, d: str) -> dict:
    row = db.execute(
        "SELECT COALESCE(SUM(kcal),0) kcal, COALESCE(SUM(protein),0) protein, "
        "COALESCE(SUM(fat),0) fat, COALESCE(SUM(carb),0) carb FROM logs WHERE user_id=? AND date=?",
        (user_id, d),
    ).fetchone()
    return {k: round(row[k], 1) for k in ("kcal", "protein", "fat", "carb")}


# ---------- Auth ----------

class LoginIn(BaseModel):
    username: str
    pin: str


FAILED_LOGINS: dict[str, list[float]] = {}
MAX_FAILS, LOCK_SECONDS = 5, 15 * 60


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    t = time.time()
    fails = [f for f in FAILED_LOGINS.get(ip, []) if t - f < LOCK_SECONDS]
    if len(fails) >= MAX_FAILS:
        raise HTTPException(429, "Terlalu banyak percobaan. Coba lagi 15 menit lagi.")
    username = body.username.strip().lower()
    if not secrets.compare_digest(USERS.get(username, "\0"), body.pin.strip()):
        FAILED_LOGINS[ip] = fails + [t]
        raise HTTPException(401, "Username atau PIN salah")
    FAILED_LOGINS.pop(ip, None)
    request.session["user"] = username
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


# ---------- Profil ----------

class ProfileIn(BaseModel):
    display_name: str | None = None
    sex: str | None = Field(None, pattern="^(L|P)$")
    birth_year: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    activity: str | None = Field(None, pattern="^(minim|ringan|sedang|berat)$")
    goal: str | None = Field(None, pattern="^(turun|jaga|naik)$")
    target_kcal: int | None = None


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user_payload(user)


@app.put("/api/me")
def update_me(body: ProfileIn, user=Depends(current_user)):
    fields = body.model_dump(exclude_unset=True)
    if fields:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with get_db() as db:
            db.execute(f"UPDATE users SET {sets} WHERE id = ?", (*fields.values(), user["id"]))
            if fields.get("weight_kg"):
                db.execute(
                    "INSERT INTO weights (user_id, date, weight_kg) VALUES (?, ?, ?) "
                    "ON CONFLICT(user_id, date) DO UPDATE SET weight_kg = excluded.weight_kg",
                    (user["id"], today(), fields["weight_kg"]),
                )
        user = {**user, **fields}
    return user_payload(user)


# ---------- Scan ----------

@app.post("/api/scan")
async def scan(image: UploadFile = File(...), hint: str = Form(""), user=Depends(current_user)):
    raw = await image.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "Foto terlalu besar (maks 8 MB)")
    mime = image.content_type or "image/jpeg"
    data_url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"

    result = await ai.analyze_food_image(data_url, hint.strip())

    items = result["items"]
    with get_db() as db:
        for item in items:
            # Kata pertama = kata utama ("air putih" -> "air"). Kandidat wajib memuatnya,
            # supaya "air putih" tidak dicocokkan ke "paria putih" hanya karena kata "putih".
            head = item["name"].lower().split()[0] if item["name"].split() else ""
            item["candidates"] = [
                c for c in search_foods(db, item["name"], limit=20)
                if any(w == head or (len(head) >= 4 and w.startswith(head)) for w in re.findall(r"[a-z0-9]+", c["name"].lower()))
            ][:12]
            # Minuman hampir 0 kkal (air putih, teh/kopi tawar) tidak perlu dicocokkan ke TKPI
            if item["per100g"]["kcal"] < 5:
                item["candidates"] = []

    # AI memilih entri database yang paling sesuai; kalau gagal, pakai skor kemiripan
    try:
        picks = await ai.pick_matches(items) if any(i["candidates"] for i in items) else [None] * len(items)
    except ai.AIError:
        picks = [c["candidates"][0]["id"] if c["candidates"] and c["candidates"][0]["score"] >= 0.8 else None for c in items]

    for item, pick in zip(items, picks):
        cands = item.pop("candidates")
        # Pengaman: tolak pilihan AI yang namanya terlalu jauh (mis. "air putih" -> "labu air")
        if pick and not any(c["id"] == pick and c["score"] >= 0.5 for c in cands):
            pick = None
        chosen = [c for c in cands if c["id"] == pick]
        item["matches"] = chosen + [c for c in cands if c["id"] != pick][:5]
        item["food_id"] = pick
    return {**result, "meal": default_meal(now().hour)}


@app.get("/api/foods")
def foods(q: str, user=Depends(current_user)):
    with get_db() as db:
        return search_foods(db, q, limit=15)


# ---------- Log makan ----------

class LogItem(BaseModel):
    food_id: int | None = None
    name: str
    grams: float = Field(gt=0, le=5000)
    per100g: dict[str, float] | None = None


class LogIn(BaseModel):
    meal: str = Field(pattern="^(sarapan|siang|malam|camilan)$")
    date: str | None = None
    items: list[LogItem]


@app.post("/api/logs")
def add_logs(body: LogIn, user=Depends(current_user)):
    d = body.date or today()
    t = now().strftime("%H:%M")
    with get_db() as db:
        for it in body.items:
            food = None
            if it.food_id:
                row = db.execute("SELECT * FROM foods WHERE id = ?", (it.food_id,)).fetchone()
                food = dict(row) if row else None
            if food:
                n, name, source = nutrients_for(food, it.grams), food["name"], "db"
            else:
                n, name, source = nutrients_for(it.per100g or {}, it.grams), it.name, "ai"
            db.execute(
                "INSERT INTO logs (user_id, date, time, meal, food_id, name, grams, kcal, protein, fat, carb, source) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (user["id"], d, t, body.meal, food["id"] if food else None, name, it.grams,
                 n["kcal"], n["protein"], n["fat"], n["carb"], source),
            )
    return {"ok": True}


class LogPatch(BaseModel):
    grams: float = Field(gt=0, le=5000)


@app.patch("/api/logs/{log_id}")
def patch_log(log_id: int, body: LogPatch, user=Depends(current_user)):
    with get_db() as db:
        row = db.execute("SELECT * FROM logs WHERE id=? AND user_id=?", (log_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "Tidak ditemukan")
        f = body.grams / row["grams"]
        db.execute(
            "UPDATE logs SET grams=?, kcal=?, protein=?, fat=?, carb=? WHERE id=?",
            (body.grams, *(round(row[k] * f, 1) for k in ("kcal", "protein", "fat", "carb")), log_id),
        )
    return {"ok": True}


@app.delete("/api/logs/{log_id}")
def delete_log(log_id: int, user=Depends(current_user)):
    with get_db() as db:
        db.execute("DELETE FROM logs WHERE id=? AND user_id=?", (log_id, user["id"]))
    return {"ok": True}


@app.get("/api/day")
def day(date: str | None = None, user=Depends(current_user)):
    d = date or today()
    with get_db() as db:
        logs = db.execute(
            "SELECT * FROM logs WHERE user_id=? AND date=? ORDER BY time", (user["id"], d)
        ).fetchall()
        totals = day_totals(db, user["id"], d)
    return {"date": d, "logs": [dict(r) for r in logs], "totals": totals, **user_payload(user)}


@app.get("/api/couple")
def couple(user=Depends(current_user)):
    """Ringkasan hari ini untuk semua akun (biar bisa saling semangatin)."""
    d = today()
    out = []
    with get_db() as db:
        for row in db.execute("SELECT * FROM users").fetchall():
            u = dict(row)
            out.append({
                "name": u["display_name"] or u["username"],
                "me": u["id"] == user["id"],
                "kcal": day_totals(db, u["id"], d)["kcal"],
                "target": (user_payload(u)["targets"] or {}).get("kcal"),
            })
    return out


# ---------- Riwayat & berat badan ----------

@app.get("/api/history")
def history(days: int = 14, user=Depends(current_user)):
    days = max(1, min(days, 120))
    start = (now().date() - timedelta(days=days - 1)).isoformat()
    with get_db() as db:
        rows = {
            r["date"]: dict(r)
            for r in db.execute(
                "SELECT date, ROUND(SUM(kcal)) kcal, ROUND(SUM(protein)) protein, ROUND(SUM(fat)) fat, "
                "ROUND(SUM(carb)) carb FROM logs WHERE user_id=? AND date>=? GROUP BY date",
                (user["id"], start),
            ).fetchall()
        }
        weights = [
            dict(r) for r in db.execute(
                "SELECT date, weight_kg FROM weights WHERE user_id=? ORDER BY date DESC LIMIT 60", (user["id"],)
            ).fetchall()
        ][::-1]
    series = []
    for i in range(days):
        d = (date_cls.fromisoformat(start) + timedelta(days=i)).isoformat()
        series.append(rows.get(d, {"date": d, "kcal": 0, "protein": 0, "fat": 0, "carb": 0}))
    return {"days": series, "weights": weights, **user_payload(user)}


class WeightIn(BaseModel):
    weight_kg: float = Field(gt=20, lt=400)
    date: str | None = None


@app.post("/api/weights")
def add_weight(body: WeightIn, user=Depends(current_user)):
    d = body.date or today()
    with get_db() as db:
        db.execute(
            "INSERT INTO weights (user_id, date, weight_kg) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, date) DO UPDATE SET weight_kg = excluded.weight_kg",
            (user["id"], d, body.weight_kg),
        )
        db.execute("UPDATE users SET weight_kg=? WHERE id=?", (body.weight_kg, user["id"]))
    return {"ok": True}


# ---------- Chat coach ----------

class ChatIn(BaseModel):
    messages: list[dict]


@app.post("/api/chat")
async def chat(body: ChatIn, user=Depends(current_user)):
    p = user_payload(user)
    d = today()
    with get_db() as db:
        logs = db.execute(
            "SELECT meal, name, grams, kcal FROM logs WHERE user_id=? AND date=? ORDER BY time", (user["id"], d)
        ).fetchall()
        totals = day_totals(db, user["id"], d)
        week = db.execute(
            "SELECT date, ROUND(SUM(kcal)) kcal FROM logs WHERE user_id=? AND date>=? GROUP BY date",
            (user["id"], (now().date() - timedelta(days=6)).isoformat()),
        ).fetchall()
    u = p["user"]
    ctx = [
        f"Tanggal & jam sekarang: {now():%Y-%m-%d %H:%M}",
        f"Profil: {u['display_name']}, jenis kelamin {u['sex']}, umur {p['age']}, tinggi {u['height_cm']} cm, "
        f"berat {u['weight_kg']} kg, aktivitas {u['activity']}, tujuan {u['goal']} berat badan.",
        f"Target harian: {p['targets']}",
        f"Total hari ini: {totals}",
        "Makanan hari ini: " + ("; ".join(f"{r['meal']}: {r['name']} {r['grams']:.0f}g ({r['kcal']:.0f} kkal)" for r in logs) or "belum ada"),
        "Kalori 7 hari terakhir: " + (", ".join(f"{r['date']}={r['kcal']:.0f}" for r in week) or "belum ada data"),
    ]
    async def gen():
        try:
            async for piece in ai.coach_stream("DATA USER:\n" + "\n".join(ctx), body.messages):
                yield piece
        except (ai.AIError, httpx.HTTPError) as e:
            yield f"\n\n⚠️ {e}"

    # Jawaban dikirim sepotong-sepotong; X-Accel-Buffering mencegah Nginx menahan stream
    return StreamingResponse(
        gen(), media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- Frontend (PWA) ----------
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
