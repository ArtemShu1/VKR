# DBF ЦБ: формы 101, 102 и 135 (2007–2021)

`sources.txt` содержит официальные URL архивов Банка России для дат 01.01, 01.04, 01.07 и 01.10 за 2007–2021 годы. Архивы включают DBF статистики соответствующей формы; вспомогательные описания форматов в этот список не включены.

В каталоге 166 архивов: форма 101 — 60, форма 102 — 60, форма 135 — 46. Для ранних периодов ЦБ не публикует форму 135.

Загрузка в Python:

```python
from pathlib import Path
import requests

out = Path("data/cbr_dbf_2007_2021/raw")
out.mkdir(parents=True, exist_ok=True)
for url in Path("data/cbr_dbf_2007_2021/sources.txt").read_text().splitlines():
    target = out / url.rsplit("/", 1)[-1]
    if not target.exists():
        target.write_bytes(requests.get(url, timeout=120).content)
```

После распаковки RAR/ZIP оставляйте только DBF, относящиеся к форме и дате архива.
