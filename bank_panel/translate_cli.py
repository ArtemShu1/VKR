from __future__ import annotations

import argparse

from .translate import translate_csv, translate_excel


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate panel headers and units into Russian")
    parser.add_argument("--xlsx", default="data/processed/bank_panel_2007_2021.xlsx")
    parser.add_argument("--csv", default="data/processed/bank_panel_2007_2021.csv")
    parser.add_argument("--out-xlsx", default="data/processed/bank_panel_2007_2021_ru.xlsx")
    parser.add_argument("--out-csv", default="data/processed/bank_panel_2007_2021_ru.csv")
    parser.add_argument("--config", default="config/indicators.yml")
    args = parser.parse_args()
    translate_excel(args.xlsx, args.out_xlsx, args.config)
    translate_csv(args.csv, args.out_csv, args.config)
    print(f"Wrote Russian files: {args.out_xlsx} and {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
