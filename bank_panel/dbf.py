from __future__ import annotations

import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

import libarchive
import pandas as pd
from dbfread import DBF


def archive_members(path: str | Path) -> Iterator[tuple[str, bytes]]:
    path = Path(path)
    if path.suffix.casefold() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.casefold().endswith(".dbf"):
                    yield name, archive.read(name)
        return
    with libarchive.file_reader(str(path)) as entries:
        for entry in entries:
            if entry.pathname.casefold().endswith(".dbf"):
                yield entry.pathname, b"".join(entry.get_blocks())


def read_dbf_bytes(content: bytes, *, encoding: str = "cp866") -> pd.DataFrame:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "data.dbf"
        path.write_bytes(content)
        return pd.DataFrame(iter(DBF(str(path), encoding=encoding, char_decode_errors="replace")))


def read_archive(path: str | Path, *, encoding: str = "cp866") -> dict[str, pd.DataFrame]:
    return {Path(name).name.upper(): read_dbf_bytes(content, encoding=encoding) for name, content in archive_members(path)}
