import json
import re

import httpx

from .config import AI_API_KEY, AI_BASE_URL, AI_CHAT_MODEL, AI_VISION_MODEL


class AIError(Exception):
    pass


async def chat_completion(model: str, messages: list[dict], temperature: float = 0.3) -> str:
    if not AI_BASE_URL or not model:
        raise AIError("AI_BASE_URL / model belum diisi di .env")
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            f"{AI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {AI_API_KEY}"},
            json={"model": model, "messages": messages, "temperature": temperature, "stream": False},
        )
    if resp.status_code != 200:
        raise AIError(f"API AI error {resp.status_code}: {resp.text[:300]}")
    text = resp.text
    # Beberapa router (mis. 9router) tetap membalas dalam format streaming SSE
    if text.lstrip().startswith("data:"):
        return _join_sse(text)
    try:
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, ValueError) as e:
        raise AIError(f"Respons AI tidak terduga: {text[:300]}") from e


def _join_sse(text: str) -> str:
    parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if chunk.get("error"):
            raise AIError(f"API AI error: {str(chunk['error'])[:300]}")
        for choice in chunk.get("choices", []):
            parts.append((choice.get("delta") or choice.get("message") or {}).get("content") or "")
    return "".join(parts)


def extract_json(text: str) -> dict:
    """Ambil objek JSON dari jawaban model (kadang dibungkus ```json atau teks lain)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise AIError(f"AI tidak mengembalikan JSON yang valid: {text[:300]}") from e


VISION_PROMPT = """Kamu adalah ahli gizi yang menganalisis foto makanan/minuman (konteks: Indonesia).
Identifikasi SETIAP item makanan/minuman yang terlihat secara terpisah (mis. nasi, lauk, sayur, sambal, minuman).
Perkirakan berat tiap item dalam gram berdasarkan ukuran piring/alat makan sebagai acuan.

Balas HANYA dengan JSON, tanpa teks lain, dengan format:
{
  "items": [
    {
      "name": "nama makanan Bahasa Indonesia, sebut bahan utama + cara masak, mis. 'nasi', 'ayam goreng paha', 'telur dadar', 'tempe goreng'",
      "grams": 150,
      "portion": "deskripsi porsi, mis. '1 piring sedang'",
      "confidence": 0.8,
      "per100g": {"kcal": 0, "protein": 0, "fat": 0, "carb": 0},
      "box_2d": [120, 250, 680, 760]
    }
  ],
  "note": "catatan singkat bila ada (mis. minyak/santan tersembunyi), boleh kosong"
}
"per100g" adalah perkiraanmu untuk nilai gizi per 100 gram (dipakai hanya jika data ahli gizi tidak punya item tsb).
"box_2d" adalah kotak pembatas item tsb di foto: [ymin, xmin, ymax, xmax], dinormalisasi 0-1000
(0,0 = pojok kiri atas). Kotak harus memuat seluruh item (untuk minuman: seluruh gelas/botolnya).
Jika foto bukan makanan/minuman, balas {"items": [], "note": "bukan makanan"}."""


async def analyze_food_image(image_data_url: str, hint: str = "") -> dict:
    content = [{"type": "text", "text": VISION_PROMPT + (f"\n\nInfo tambahan dari user: {hint}" if hint else "")}]
    content.append({"type": "image_url", "image_url": {"url": image_data_url}})
    text = await chat_completion(AI_VISION_MODEL, [{"role": "user", "content": content}], temperature=0.1)
    data = extract_json(text)
    items = []
    for it in data.get("items", []):
        try:
            items.append({
                "name": str(it.get("name", "")).strip(),
                "grams": float(it.get("grams") or 100),
                "portion": str(it.get("portion", "")),
                "confidence": float(it.get("confidence") or 0.5),
                "per100g": {k: float((it.get("per100g") or {}).get(k) or 0) for k in ("kcal", "protein", "fat", "carb")},
                "box": parse_box(it.get("box_2d") or it.get("box")),
            })
        except (TypeError, ValueError):
            continue
    items = [i for i in items if i["name"]]
    return {"items": items, "note": data.get("note", ""), "crop": union_box([i["box"] for i in items])}


def parse_box(raw) -> list[float] | None:
    """[ymin, xmin, ymax, xmax] skala 0-1000 -> [x, y, w, h] skala 0-1, atau None kalau tidak valid."""
    try:
        ymin, xmin, ymax, xmax = (min(max(float(v), 0), 1000) / 1000 for v in raw)
    except (TypeError, ValueError):
        return None
    if xmax - xmin < 0.02 or ymax - ymin < 0.02:
        return None
    return [round(xmin, 4), round(ymin, 4), round(xmax - xmin, 4), round(ymax - ymin, 4)]


def union_box(boxes: list, pad: float = 0.06) -> list[float] | None:
    """Gabungan semua kotak item + sedikit ruang di tepi. None kalau tidak perlu dipotong."""
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    x1 = max(min(b[0] for b in boxes) - pad, 0)
    y1 = max(min(b[1] for b in boxes) - pad, 0)
    x2 = min(max(b[0] + b[2] for b in boxes) + pad, 1)
    y2 = min(max(b[1] + b[3] for b in boxes) + pad, 1)
    if (x2 - x1) * (y2 - y1) > 0.85:  # makanan sudah memenuhi foto
        return None
    return [round(x1, 4), round(y1, 4), round(x2 - x1, 4), round(y2 - y1, 4)]


async def pick_matches(items: list[dict]) -> list[int | None]:
    """Minta AI memilih entri database gizi yang paling sesuai untuk tiap item hasil scan."""
    lines = []
    for i, it in enumerate(items):
        cands = "; ".join(f"{m['id']}={m['name']}" for m in it["candidates"]) or "(tidak ada)"
        lines.append(f"Item {i}: \"{it['name']}\" ({it.get('portion', '')}). Kandidat: {cands}")
    prompt = (
        "Untuk setiap item makanan hasil foto, pilih ID kandidat dari database gizi (TKPI) yang PALING SESUAI "
        "sebagai makanan siap santap (perhatikan jenis bahan, bagian, dan cara masak). "
        "Pilih null jika tidak ada kandidat yang benar-benar sesuai (jangan memaksakan, mis. 'usus ayam' bukan 'ayam goreng').\n\n"
        + "\n".join(lines)
        + '\n\nBalas HANYA JSON: {"picks": [id_atau_null, ...]} sesuai urutan item.'
    )
    text = await chat_completion(AI_CHAT_MODEL, [{"role": "user", "content": prompt}], temperature=0)
    picks = extract_json(text).get("picks", [])
    out = []
    for i, it in enumerate(items):
        valid = {m["id"] for m in it["candidates"]}
        p = picks[i] if i < len(picks) else None
        out.append(int(p) if isinstance(p, (int, str)) and str(p).isdigit() and int(p) in valid else None)
    return out


async def coach_reply(system_context: str, history: list[dict]) -> str:
    system = (
        "Kamu adalah 'Coach', pendamping diet yang ramah, santai, dan suportif untuk dua orang pasangan. "
        "Jawab dalam Bahasa Indonesia yang santai dan ringkas. Berikan saran praktis berbasis data di bawah. "
        "Jangan memberi diagnosis medis; sarankan ke dokter/ahli gizi bila menyangkut kondisi kesehatan.\n\n"
        + system_context
    )
    msgs = [{"role": "system", "content": system}] + [
        {"role": m["role"], "content": str(m["content"])[:4000]}
        for m in history[-12:]
        if m.get("role") in ("user", "assistant")
    ]
    text = await chat_completion(AI_CHAT_MODEL, msgs, temperature=0.6)
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
