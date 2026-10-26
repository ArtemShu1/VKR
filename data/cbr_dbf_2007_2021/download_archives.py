from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)
for url in (ROOT / "sources.txt").read_text().splitlines():
    target = RAW / url.rsplit("/", 1)[-1]
    if not target.exists():
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        target.write_bytes(response.content)
        print(target)
