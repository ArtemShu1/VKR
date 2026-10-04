from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import IndicatorSpec


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_indicator_specs(path: str | Path) -> list[IndicatorSpec]:
    raw = load_yaml(path)
    return [
        IndicatorSpec(
            name=item["name"],
            label=item["label"],
            form=str(item.get("form", "")),
            aliases=tuple(item.get("aliases", [])),
        )
        for item in raw.get("indicators", [])
    ]
