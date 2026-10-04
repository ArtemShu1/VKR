import io

import pandas as pd

from bank_panel.export import append_rows, stable_columns
from bank_panel.normalize import is_group_label, parse_number
from bank_panel.validation import validate_panel


def test_parse_russian_numbers():
    assert parse_number("1 234,50") == 1234.5
    assert parse_number("—") is None


def test_group_indicators_are_rejected():
    assert is_group_label("Н20.1 норматив банковской группы")
    frame = pd.DataFrame({"regn_gko": [1], "bank_name": ["A"], "year": [2007], "n11": [10]})
    assert validate_panel(frame) == []


def test_append_deduplicates_bank_year():
    a = pd.DataFrame({"regn_gko": [1], "bank_name": ["A"], "year": [2007], "x": [1]})
    b = pd.DataFrame({"regn_gko": [1], "bank_name": ["A"], "year": [2007], "x": [2]})
    assert append_rows(a, b).iloc[0]["x"] == 2


def test_stable_columns_keys_first():
    frame = pd.DataFrame({"year": [2007], "z": [1], "bank_name": ["A"], "regn_gko": [1], "z__source": ["cbr"]})
    assert stable_columns(frame)[:3] == ["regn_gko", "bank_name", "year"]
