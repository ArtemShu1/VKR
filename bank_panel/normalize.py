from __future__ import annotations

import math
import re
from typing import Any


def norm_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).replace("\xa0", " ").replace("ё", "е").replace("Ё", "Е")
    return re.sub(r"\s+", " ", text).strip().casefold()


def parse_number(value: Any) -> float | int | None:
    """Parse Russian decimal/thousands notation without changing missing markers."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip().replace("\xa0", " ")
    if not text or text in {"-", "—", "–", ".", "..", "н/д", "нет данных"}:
        return None
    text = text.replace("%", "").replace(" ", "")
    # Russian exports use comma as decimal separator. Keep a leading minus.
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        text = text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def is_group_label(value: Any) -> bool:
    text = norm_text(value)
    return bool(re.search(r"\bn20(?:\.\d+)?\b|банковск(?:ая|ой) групп", text))


def match_label(value: Any, aliases: tuple[str, ...]) -> bool:
    text = norm_text(value)
    if not text or is_group_label(text):
        return False
    return any(norm_text(alias) in text or text in norm_text(alias) for alias in aliases)
