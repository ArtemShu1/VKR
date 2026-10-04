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


def _normalise_code(value: object) -> str:
    """Return a CBR row/account code without DBF numeric artefacts."""
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") and text[:-2].isdigit() else text


def _choose_source_rows(result: pd.DataFrame, code_col: str, value_col: str, codes: tuple[str, ...]) -> pd.DataFrame:
    """Select the first available official row for each bank.

    Some CBR forms publish mutually exclusive rows (for example, profit and
    loss) and put zero in the inapplicable row.  We preserve the value from
    the applicable row and retain its code in the provenance column; no
    arithmetic or sign conversion is performed.
    """
    work = result.copy()
    work["_cbr_code"] = work[code_col].map(_normalise_code)
    work["_cbr_value"] = pd.to_numeric(work[value_col], errors="coerce")
    work = work[work["_cbr_code"].isin(codes)].copy()
    if work.empty:
        return work
    # Prefer a non-zero value when a profit/loss pair is present.  Zero is a
    # legitimate value, so it remains the fallback if all alternatives are 0.
    work["_nonzero"] = work["_cbr_value"].notna() & work["_cbr_value"].ne(0)
    work["_order"] = work["_cbr_code"].map({code: index for index, code in enumerate(codes)})
    work = work.sort_values(["regn_gko", "_nonzero", "_order"], ascending=[True, False, True])
    return work.drop_duplicates("regn_gko", keep="first")


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
    t102: dict[str, pd.DataFrame] = {}
    if form135:
        t135 = read_archive(form135)
        names = _find_table(t135, "_135B.DBF")
        ratios = _find_table(t135, "_135_3.DBF")
    else:
        ratios = None
    # Form 135 was introduced after the earliest requested years. Form 102's
    # individual NP/N registry is the official fallback for 2007-2010.
    if names is None and form102:
        t102 = read_archive(form102)
        names = _find_table(t102, "NP1.DBF")
        if names is None:
            names = _find_table(t102, "_NP.DBF")
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
            # B1 is the detailed bank-by-account table.  Some older archives
            # contain a small *_B summary table as well; choosing it first
            # silently drops almost all banks.
            balance = next((v for k, v in t101.items() if k.endswith("B1.DBF")), None)
            if balance is None:
                balance = next((v for k, v in t101.items() if k.endswith("_B.DBF")), None)
            if balance is not None:
                value_col = "ITOGO" if "ITOGO" in balance.columns else ("VITG" if "VITG" in balance.columns else None)
                if value_col:
                    account_col = "NUM_SC"
                    regn_col = "REGN"
                    account_map = {
                        "charter_capital": ("102",),
                        "accounting_equity": ("102", "103", "104", "105", "106", "107", "108", "109"),
                        "additional_capital": ("106",),
                        "retained_earnings_prior_years": ("108",),
                        "cash": ("202",),
                        "cbr_accounts": ("30102",),
                        "interbank_placements": ("320", "321", "322", "323"),
                        "loans_individuals": ("455",),
                        "overdue_loans": ("458", "459"),
                        "securities": ("501", "502", "503", "504", "505", "506"),
                        "government_local_debt": ("50305", "50306"),
                        # These are account-plan headings in form 0409101.
                        # Values are grouped only by the explicit CBR account
                        # prefixes; no balance-sheet identity is calculated.
                        "loan_portfolio": tuple(str(code) for code in range(441, 460)),
                        "loans_legal_entities": tuple(str(code) for code in range(441, 455)) + ("456",),
                        "deposits_total": tuple(str(code) for code in range(410, 441)),
                        "corporate_deposits": tuple(str(code) for code in range(410, 423)) + ("425",),
                        "household_deposits": ("423", "426"),
                        "reserves": ("10630", "10631", "20321", "30126", "30226"),
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
    # A small set of non-ratio measures is published in section 2 of the same
    # individual form.  The code Лам is the CBR's high-liquid-assets line
    # (used directly in the liquidity reporting); retain the original code.
    if form135:
        try:
            measures = _find_table(t135, "_135_2.DBF")
            if measures is not None and {"REGN", "C1_2", "C2_2"}.issubset(measures.columns):
                measures = measures.assign(regn_gko=measures["REGN"].map(_normalise_code))
                measure_map = {"Лам": "highly_liquid_assets"}
                for source_code, column_name in measure_map.items():
                    selected = measures[measures["C1_2"].astype(str).str.strip() == source_code]
                    if selected.empty:
                        continue
                    vals = pd.to_numeric(selected.drop_duplicates("regn_gko").set_index("regn_gko")["C2_2"], errors="coerce")
                    frame[column_name] = frame["regn_gko"].map(vals)
                    frame[f"{column_name}__unit"] = "thousand RUB"
                    frame[f"{column_name}__form"] = "0409135"
                    frame[f"{column_name}__row_code"] = source_code
                    frame[f"{column_name}__source"] = source_base + " (form 0409135)"
        except Exception as exc:
            log.warning("Could not map form 135 section 2 measures %s: %s", form135, exc)
    # Form 102 contains code/value rows. Preserve code-level provenance and map
    # official section totals and result rows. Missing forms remain explicit
    # NaN rather than being reconstructed from other rows.
    if form102:
        try:
            if not t102:
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
                result = result.assign(regn_gko=result[regn].map(_normalise_code))
                # Row codes are stable in the CBR form even when the visible
                # labels and the set of sections change between years.  The
                # two-code pairs are mutually exclusive profit/loss (or
                # increase/decrease) rows and are selected without changing
                # the published values.
                row_map: dict[str, tuple[str, ...]] = {
                    "interest_income_total": ("11000",),
                    "commission_income": ("12000",),
                    # The CBR changed the numbering of the OФР sections:
                    # 2007 uses 10000/20000/33001, 2008–2015 uses
                    # 10000/20000/31001, and the current form uses the
                    # 10001–10004/61101 codes.
                    "other_operating_income": ("16000", "28000"),
                    "interest_expense_total": ("21000", "31000"),
                    "commission_expense": ("22000", "32000", "33000"),
                    "operating_expenses": ("10004", "20000"),
                    "pretax_profit": ("01000", "02000"),
                    "income_tax_expense": ("03000", "04000", "28201", "28202", "28101"),
                    "net_profit": ("61101", "61102", "31001", "31002", "33001", "33002"),
                    "comprehensive_income": ("40000", "50000"),
                    "profit_and_comprehensive_income": ("81201", "81202"),
                }
                for spec in specs:
                    if spec.form != "0409102" or spec.name not in row_map:
                        continue
                    codes = row_map[spec.name]
                    selected = _choose_source_rows(result, code, value, codes)
                    if selected.empty:
                        continue
                    vals = selected.set_index("regn_gko")["_cbr_value"]
                    row_codes = selected.set_index("regn_gko")["_cbr_code"]
                    frame[spec.name] = frame["regn_gko"].map(vals)
                    frame[f"{spec.name}__unit"] = "thousand RUB"
                    frame[f"{spec.name}__form"] = "0409102"
                    # A bank can use either row of an exclusive pair. Keep the
                    # exact selected code for auditability.
                    frame[f"{spec.name}__row_code"] = frame["regn_gko"].map(row_codes)
                    frame[f"{spec.name}__source"] = source_base + " (form 0409102)"
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
