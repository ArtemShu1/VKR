#!/usr/bin/env python
"""Build the reproducible bank-year panel from downloaded CBR archives."""
from bank_panel.build import build_from_directory


if __name__ == "__main__":
    build_from_directory(
        "data/raw",
        "data/processed/bank_panel_2007_2021.xlsx",
        "data/processed/bank_panel_2007_2021.csv",
    )
