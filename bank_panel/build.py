from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_indicator_specs, load_yaml
from .dbf import read_archive
from .export import write_outputs
from .models import CellValue, IndicatorSpec

log = logging.getLogger(__name__)


def _find_table(tables: dict[str, pd.DataFrame], suffix: str) -> pd.DataFrame | None:
    for name, frame in tables.items():
        if name.endswith(suffix.upper()):
            return frame
    return None


def records_from_cbr_archives(
    *,
    year: int,
    form101: str | Path | None = None,
    form102: str | Path | None = None,
    form135: str | Path | None = None,
    form123: str | Path | None = None,
    specs: list[IndicatorSpec],
    source_base: str = "https://www.cbr.ru/banking_sector/otchetnost-kreditnykh-organizaciy/",
) -> pd.DataFrame:
    """Build a bank-year frame from CBR DBF archives.

    Form 135 supplies the official individual-bank name and REGN_GKO. Form 102
    and form 101 are parsed into long source tables; the mapping of CBR codes
    can be extended in `config/code_map.yml` without changing the pipeline.
    """
    names: pd.DataFrame | None = None
    if form135:
        t135 = read_archive(form135)
        names = _find_table(t135, "_135B.DBF")
        ratios = _find_table(t135, "_135_3.DBF")
    else:
        ratios = None
    # Form 135 was introduced after the earliest requested years. Form 102's
    # individual NP/N registry is the official fallback for 2007-2010.
    if names is None and form102:
        t102_for_names = read_archive(form102)
        names = _find_table(t102_for_names, "NP1.DBF")
        if names is None:
            names = _find_table(t102_for_names, "_NP.DBF")
    if names is None:
        raise ValueError("no individual bank registry table found in form 135 or form 102")
    names = names.rename(columns={"REGN": "regn_gko", "NAME_B": "bank_name"})[["regn_gko", "bank_name"]]
    names["regn_gko"] = names["regn_gko"].astype(str).str.replace(r"\.0$", "", regex=True)
    names = names.drop_duplicates("regn_gko")
    frame = names.assign(year=year)
    if form123:
        try:
            t123 = read_archive(form123)
            capital = next((v for k, v in t123.items() if k.endswith("_123D.DBF")), None)
            if capital is not None and {"REGN", "C1", "C3"}.issubset(capital.columns):
                capital = capital.assign(regn_gko=capital["REGN"].astype(str).str.replace(r"\.0$", "", regex=True))
                vals = capital[capital["C1"].astype(str).str.strip() == "000"].set_index("regn_gko")["C3"]
                frame["regulatory_capital"] = frame["regn_gko"].map(vals)
                frame["regulatory_capital__unit"] = "thousand RUB"
                frame["regulatory_capital__form"] = "0409123"
                frame["regulatory_capital__row_code"] = "000"
                frame["regulatory_capital__source"] = source_base + " (form 0409123)"
        except Exception as exc:
            log.warning("Could not read form 123 archive %s: %s", form123, exc)
    # Verified account-plan aggregates from individual form 101 (amounts are
    # thousand RUB in the CBR export). Prefix sums are used only where the CBR
    # account plan explicitly defines the heading; no balance-sheet identity is
    # inferred by subtracting unrelated totals.
    if form101:
        try:
            t101 = read_archive(form101)
            balance = next((v for k, v in t101.items() if k.endswith("_B.DBF") or k.endswith("B1.DBF")), None)
            if balance is not None:
                value_col = "ITOGO" if "ITOGO" in balance.columns else ("VITG" if "VITG" in balance.columns else None)
                if value_col:
                    account_col = "NUM_SC"
                    regn_col = "REGN"
                    account_map = {
                        "charter_capital": ("102",),
                        "additional_capital": ("106",),
                        "retained_earnings_prior_years": ("108",),
                        "cash": ("202",),
                        "cbr_accounts": ("30102",),
                        "interbank_placements": ("320", "321", "322", "323"),
                        "loans_individuals": ("455",),
                        "securities": ("501", "502", "503", "504", "505", "506"),
                        "mandatory_reserves_cbr": ("30201", "30202", "30203", "30204"),
                    }
                    normalized = balance[account_col].astype(str).str.replace(r"\.0$", "", regex=True)
                    balance = balance.assign(regn_gko=balance[regn_col].astype(str).str.replace(r"\.0$", "", regex=True), _account=normalized)
                    for column_name, prefixes in account_map.items():
                        selected = balance[balance["_account"].apply(lambda x: any(x == p or x.startswith(p) for p in prefixes))]
                        vals = selected.groupby("regn_gko")[value_col].sum()
                        frame[column_name] = frame["regn_gko"].map(vals)
                        frame[f"{column_name}__unit"] = "thousand RUB"
                        frame[f"{column_name}__form"] = "0409101"
                        frame[f"{column_name}__row_code"] = ",".join(prefixes)
                        frame[f"{column_name}__source"] = source_base + " (form 0409101)"
        except Exception as exc:
            log.warning("Could not read form 101 archive %s: %s", form101, exc)
    # Form 135 section 3 stores one row per REGN and individual N-code.
    if ratios is not None:
        ratio_code = next((c for c in ratios.columns if c.startswith("C1_3")), None)
        ratio_value = next((c for c in ratios.columns if c.startswith("C2_3")), None)
        if ratio_code and ratio_value:
            keep = ratios[ratios[ratio_code].astype(str).str.upper().str.startswith("Н1")].copy()
            keep["regn_gko"] = keep["REGN"].astype(str).str.replace(r"\.0$", "", regex=True)
            names_by_code = {"Н1.0": "n10", "Н1.1": "n11", "Н1.2": "n12", "Н1.4": "n14"}
            for code, column_name in names_by_code.items():
                vals = keep[keep[ratio_code].astype(str).str.upper() == code].set_index("regn_gko")[ratio_value]
                frame[column_name] = frame["regn_gko"].map(vals)
                frame[f"{column_name}__unit"] = "percent"
                frame[f"{column_name}__form"] = "0409135"
                frame[f"{column_name}__row_code"] = code
                frame[f"{column_name}__source"] = source_base + " (form 0409135)"
    # Form 102 contains code/value rows. Preserve code-level provenance and map
    # known codes only; missing forms remain explicit NaN rather than guessed.
    if form102:
        try:
            t102 = read_archive(form102)
        except Exception as exc:
            log.warning("Could not read form 102 archive %s: %s", form102, exc)
            t102 = {}
        result = _find_table(t102, "_P1.DBF")
        if result is not None:
            regn = next((c for c in result if c.upper() == "REGN"), None)
            code = next((c for c in result if c.upper() == "CODE"), None)
            value = next((c for c in result if "ITOGO" in c.upper()), None)
            if regn and code and value:
                # 61101 is the official CBR code for profit after tax.
                subset = result[result[code].astype(str).isin(["61101", "61102"])].copy()
                subset["regn_gko"] = subset[regn].astype(str).str.replace(r"\.0$", "", regex=True)
                vals = subset.groupby("regn_gko")[value].first()
                frame["net_profit"] = frame["regn_gko"].map(vals)
                frame["net_profit__unit"] = "thousand RUB"
                frame["net_profit__form"] = "0409102"
                frame["net_profit__row_code"] = "61101/61102"
                frame["net_profit__source"] = source_base + " (form 0409102)"
    # Always emit the complete documented schema. A missing official row is
    # represented as NA and is never silently calculated from another row.
    additions: dict[str, object] = {}
    for spec in specs:
        if spec.name not in frame:
            additions[spec.name] = pd.NA
        if f"{spec.name}__unit" not in frame:
            additions[f"{spec.name}__unit"] = pd.NA
        if f"{spec.name}__form" not in frame:
            additions[f"{spec.name}__form"] = spec.form
        if f"{spec.name}__row_code" not in frame:
            additions[f"{spec.name}__row_code"] = pd.NA
        if f"{spec.name}__source" not in frame:
            additions[f"{spec.name}__source"] = pd.NA
    if additions:
        frame = pd.concat([frame, pd.DataFrame(additions, index=frame.index)], axis=1)
    return frame


def build_from_directory(raw_dir: str | Path, output_xlsx: str | Path, output_csv: str | Path, config_path: str | Path = "config/indicators.yml") -> pd.DataFrame:
    """Build all years for which matching archives exist in raw_dir.

    Files use `<form>-<yyyymmdd>.(rar|zip)` naming from the CBR portal.
    """
    specs = load_indicator_specs(config_path)
    raw = Path(raw_dir)
    rows: list[pd.DataFrame] = []
    for year in range(2007, 2022):
        date = f"{year + 1}0101"
        paths = {form: next(iter(raw.glob(f"{form}-{date}.*")), None) for form in ("101", "102", "123", "135")}
        if not paths["135"] and not paths["102"]:
            log.warning("No individual form archive for year %s (expected %s)", year, date)
            continue
        rows.append(records_from_cbr_archives(year=year, form101=paths["101"], form102=paths["102"], form135=paths["135"], form123=paths["123"], specs=specs))
    if not rows:
        raise FileNotFoundError("No annual form 135 archives found in raw directory")
    frame = pd.concat(rows, ignore_index=True)
    write_outputs(frame, output_xlsx, output_csv)
    return frame
