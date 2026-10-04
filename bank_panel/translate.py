from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import load_indicator_specs


def russian_column_names(config_path: str | Path) -> dict[str, str]:
    specs = load_indicator_specs(config_path)
    result = {"regn_gko": "REGN_GKO", "bank_name": "Наименование кредитной организации", "year": "Год"}
    for spec in specs:
        result[spec.name] = spec.label
        result[f"{spec.name}__unit"] = f"{spec.label} — единица измерения"
        result[f"{spec.name}__form"] = f"{spec.label} — форма ЦБ"
        result[f"{spec.name}__row_code"] = f"{spec.label} — код строки"
        result[f"{spec.name}__source"] = f"{spec.label} — источник"
    return result


def translate_frame(frame: pd.DataFrame, config_path: str | Path) -> pd.DataFrame:
    translated = frame.rename(columns=russian_column_names(config_path)).copy()
    # These are descriptive text values; numeric cells are not touched.
    for column in translated.columns:
        if column.endswith(" — единица измерения"):
            translated[column] = translated[column].replace({
                "percent": "%",
                "thousand RUB": "тыс. руб.",
            })
    return translated


def translate_excel(input_path: str | Path, output_path: str | Path, config_path: str | Path) -> None:
    frame = pd.read_excel(input_path, sheet_name="bank_year")
    translated = translate_frame(frame, config_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    translated.to_excel(output_path, index=False, sheet_name="банк_год")


def translate_csv(input_path: str | Path, output_path: str | Path, config_path: str | Path) -> None:
    frame = pd.read_csv(input_path, low_memory=False)
    translated = translate_frame(frame, config_path)
    translated.to_csv(output_path, index=False, encoding="utf-8-sig")
