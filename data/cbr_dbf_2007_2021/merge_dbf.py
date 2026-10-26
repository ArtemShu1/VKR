from pathlib import Path
from io import BytesIO
import re
import zipfile
import requests
import pandas as pd
from dbfread import DBF
import rarfile

ROOT = Path("cbr_dbf_2007_2021")
RAW = ROOT / "raw"
OUT = ROOT / "combined_dbf.csv"
SOURCES = ROOT / "sources.txt"

RAW.mkdir(parents=True, exist_ok=True)

def download_archives():
    urls = [u.strip() for u in SOURCES.read_text(encoding="utf-8").splitlines() if u.strip()]
    session = requests.Session()
    for n, url in enumerate(urls, 1):
        target = RAW / url.rsplit("/", 1)[-1]
        if not target.exists():
            print(f"[{n}/{len(urls)}] скачиваю {target.name}")
            r = session.get(url, timeout=180)
            r.raise_for_status()
            target.write_bytes(r.content)
    return sorted(RAW.iterdir())

def members(path):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith(".dbf"):
                    yield Path(name).name, z.read(name)
    elif path.suffix.lower() == ".rar":
        with rarfile.RarFile(path) as r:
            for info in r.infolist():
                if info.filename.lower().endswith(".dbf"):
                    yield Path(info.filename).name, r.read(info)
    else:
        return

def read_dbf(data):
    last_error = None
    for encoding in ("cp866", "cp1251", "latin1"):
        try:
            table = DBF(
                filename=BytesIO(data),
                load=True,
                encoding=encoding,
                char_decode_errors="replace",
            )
            return pd.DataFrame(iter(table))
        except Exception as exc:
            last_error = exc
    raise last_error

def main():
    archives = download_archives()
    frames = []
    for archive in archives:
        match = re.match(r"(101|102|135)-(\d{8})", archive.name)
        if not match:
            continue
        form, date = match.groups()
        print(f"обрабатываю {archive.name}")
        for dbf_name, data in members(archive):
            frame = read_dbf(data)
            frame.insert(0, "dbf_file", dbf_name)
            frame.insert(0, "report_date", pd.to_datetime(date, format="%Y%m%d").date().isoformat())
            frame.insert(0, "form", form)
            frame.insert(0, "archive", archive.name)
            frames.append(frame)

    if not frames:
        raise RuntimeError("DBF-файлы не найдены")
    result = pd.concat(frames, ignore_index=True, sort=False)
    result = result.sort_values(["report_date", "form", "dbf_file"], kind="stable")
    result.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"Готово: {OUT}")
    print(f"Строк: {len(result):,}; столбцов: {len(result.columns)}")
    print("Формы:", result["form"].value_counts().sort_index().to_dict())
    return result

if __name__ == "__main__":
    main()
