from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .build import build_from_directory


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Russian individual-bank long panel")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--xlsx", default="data/processed/bank_panel_2007_2021.xlsx")
    parser.add_argument("--csv", default="data/processed/bank_panel_2007_2021.csv")
    parser.add_argument("--config", default="config/indicators.yml")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    frame = build_from_directory(args.raw_dir, args.xlsx, args.csv, args.config)
    print(f"Wrote {len(frame):,} bank-year observations to {args.xlsx} and {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
