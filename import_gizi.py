"""
Import database gizi dari ahli gizi (Excel .xlsx atau .csv) ke SQLite.

Contoh:
    python import_gizi.py data_gizi.xlsx
    python import_gizi.py data_gizi.csv --replace
    python import_gizi.py data_gizi.xlsx --sheet "Sheet1" --col-kcal "Energi (Kal)"
    python import_gizi.py data_gizi.xlsx --per 1   # kalau nilai gizinya per 1 porsi, bukan per 100 g

Nama kolom dideteksi otomatis dari header. Kalau salah, timpa dengan --col-xxx.
Nilai gizi disimpan sebagai per 100 gram.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

from app.db import get_db, init_db

# kolom -> kata kunci header (huruf kecil) yang dicari
FIELDS = {
    "name": ["nama bahan", "nama makanan", "nama pangan", "nama", "makanan", "food", "name", "bahan"],
    "kcal": ["energi", "kalori", "kkal", "kcal", "energy", "kal"],
    "protein": ["protein"],
    "fat": ["lemak", "fat"],
    "carb": ["karbohidrat", "karbo", "kh", "carb"],
    "fiber": ["serat", "fiber", "fibre"],
    "portion_g": ["berat porsi", "porsi (g)", "gram porsi", "berat (g)", "berat"],
    "portion_label": ["urt", "ukuran rumah tangga", "porsi", "satuan"],
}


def read_rows(path: Path, sheet: str | None) -> list[list]:
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook

        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    return list(csv.reader(text.splitlines(), dialect))


def find_header(rows: list[list]) -> tuple[list, int]:
    """Cari header (boleh tersebar di beberapa baris, mis. TKPI) -> (header gabungan, baris awal data)."""
    width = max((len(r) for r in rows[:20]), default=0)
    for i in range(min(15, len(rows))):
        # gabungkan teks baris i..i+2 per kolom
        merged = [" ".join(str(r[c]).strip() for r in rows[i:i + 3] if c < len(r) and r[c] is not None) for c in range(width)]
        cells = [c.lower() for c in merged]
        has_name = any(any(k in c for k in FIELDS["name"]) for c in cells)
        has_kcal = any(any(k in c for k in FIELDS["kcal"]) for c in cells)
        if has_name and has_kcal and any(k in str(rows[i]).lower() for k in FIELDS["name"]):
            # data mulai di baris pertama setelah i yang punya angka di kolom energi
            kcal_col = next(j for j, c in enumerate(cells) if any(k in c for k in FIELDS["kcal"]))
            start = next(
                (j for j in range(i + 1, len(rows)) if kcal_col < len(rows[j]) and to_float(rows[j][kcal_col]) is not None),
                i + 1,
            )
            # header hanya dari baris i sampai sebelum data
            header = [" ".join(str(r[c]).strip() for r in rows[i:start] if c < len(r) and r[c] is not None) for c in range(width)]
            return header, start
    return rows[0], 1


def detect_columns(header: list, overrides: dict) -> dict:
    cells = [str(c or "").strip().lower() for c in header]
    mapping, used = {}, set()
    for field, keys in FIELDS.items():
        if overrides.get(field):
            target = overrides[field].strip().lower()
            if target not in cells:
                sys.exit(f"Kolom '{overrides[field]}' tidak ditemukan. Header: {header}")
            mapping[field] = cells.index(target)
            used.add(mapping[field])
            continue
        for key in keys:  # kata kunci diurutkan dari paling spesifik
            idx = next((i for i, c in enumerate(cells) if i not in used and key in c), None)
            if idx is not None:
                mapping[field] = idx
                used.add(idx)
                break
    return mapping


def to_float(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")  # format Indonesia 12,5
    s = s.replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group()) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--sheet")
    ap.add_argument("--replace", action="store_true", help="hapus semua data makanan lama dulu")
    ap.add_argument("--per", type=float, default=100, help="nilai gizi di file per berapa gram (default 100)")
    for f in FIELDS:
        ap.add_argument(f"--col-{f.replace('_', '-')}", dest=f"col_{f}")
    args = ap.parse_args()

    rows = read_rows(Path(args.file), args.sheet)
    header, start = find_header(rows)
    mapping = detect_columns(header, {f: getattr(args, f"col_{f}") for f in FIELDS})

    print("Kolom terdeteksi:")
    for f in FIELDS:
        print(f"  {f:14} -> {header[mapping[f]]!r}" if f in mapping else f"  {f:14} -> (tidak ada)")
    if "name" not in mapping or "kcal" not in mapping:
        sys.exit("Kolom nama dan energi wajib ada. Pakai --col-name / --col-kcal.")

    factor = 100 / args.per
    records = []
    for row in rows[start:]:
        get = lambda f: row[mapping[f]] if f in mapping and mapping[f] < len(row) else None
        name = str(get("name") or "").strip()
        kcal = to_float(get("kcal"))
        if not name or kcal is None:
            continue
        records.append((
            name,
            kcal * factor,
            (to_float(get("protein")) or 0) * factor,
            (to_float(get("fat")) or 0) * factor,
            (to_float(get("carb")) or 0) * factor,
            (to_float(get("fiber")) or 0) * factor,
            to_float(get("portion_g")),
            str(get("portion_label") or "").strip() or None,
        ))

    init_db()
    with get_db() as db:
        if args.replace:
            db.execute("UPDATE logs SET food_id = NULL")
            db.execute("DELETE FROM foods")
        db.executemany(
            "INSERT INTO foods (name, kcal, protein, fat, carb, fiber, portion_g, portion_label) "
            "VALUES (?,?,?,?,?,?,?,?)",
            records,
        )
    print(f"\n{len(records)} makanan diimport. Contoh 3 baris pertama (per 100 g):")
    for r in records[:3]:
        print(f"  {r[0]}: {r[1]:.0f} kkal, P {r[2]:.1f} g, L {r[3]:.1f} g, KH {r[4]:.1f} g")


if __name__ == "__main__":
    main()
