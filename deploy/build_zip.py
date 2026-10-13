"""Buat dist/sistem-diet.zip berisi kode aplikasi (tanpa .env, database, dan .venv)."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / "sistem-diet.zip"
INCLUDE = ["app", "static", "deploy/server", "requirements.txt", "import_gizi.py", "README.md", ".env.example"]


def main():
    OUT.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for item in INCLUDE:
            path = ROOT / item
            files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
            for f in files:
                if "__pycache__" in f.parts:
                    continue
                z.write(f, f.relative_to(ROOT).as_posix())
                count += 1
    print(f"{OUT} ({count} file, {OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
