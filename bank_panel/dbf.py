from __future__ import annotations

import zipfile
import os
import shutil
import subprocess
import tempfile
import datetime
import struct
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
        try:
            return pd.DataFrame(iter(DBF(str(path), encoding=encoding, char_decode_errors="replace")))
        except (ValueError, UnicodeDecodeError, struct.error):
            return _read_dbf_tolerant(content, encoding=encoding)


def _read_dbf_tolerant(content: bytes, *, encoding: str) -> pd.DataFrame:
    """Read CBR DBF variants containing NUL padding in numeric fields."""
    record_count = struct.unpack_from("<I", content, 4)[0]
    header_length, record_length = struct.unpack_from("<HH", content, 8)
    fields: list[tuple[str, str, int]] = []
    offset = 32
    while offset + 32 <= header_length:
        descriptor = content[offset:offset + 32]
        if descriptor[0] == 0:
            break
        name = descriptor[:11].split(b"\0", 1)[0].decode("ascii", errors="replace")
        fields.append((name, chr(descriptor[11]), descriptor[16]))
        offset += 32
    rows: list[dict[str, object]] = []
    for index in range(record_count):
        start = header_length + index * record_length
        record = content[start:start + record_length]
        if len(record) < record_length or record[:1] == b"*":
            continue
        cursor = 1
        row: dict[str, object] = {}
        for name, kind, width in fields:
            raw = record[cursor:cursor + width]
            cursor += width
            raw = raw.replace(b"\x00", b"").strip()
            if not raw:
                row[name] = None
            elif kind == "N" or kind == "F":
                try:
                    number = float(raw.replace(b",", b"."))
                    row[name] = int(number) if number.is_integer() else number
                except ValueError:
                    row[name] = None
            elif kind == "D":
                try:
                    row[name] = datetime.datetime.strptime(raw.decode("ascii"), "%Y%m%d").date()
                except (ValueError, UnicodeDecodeError):
                    row[name] = None
            else:
                row[name] = raw.decode(encoding, errors="replace").strip()
        rows.append(row)
    return pd.DataFrame(rows, columns=[field[0] for field in fields])


def read_archive(path: str | Path, *, encoding: str = "cp866") -> dict[str, pd.DataFrame]:
    try:
        return {Path(name).name.upper(): read_dbf_bytes(content, encoding=encoding) for name, content in archive_members(path)}
    except Exception as first_error:
        # libarchive cannot decode some valid RAR4 blocks. 7-Zip is used as a
        # verified fallback; it preserves the DBF bytes and does not alter data.
        binary = os.environ.get("SEVENZIP_BIN") or shutil.which("7zz") or shutil.which("7z")
        if not binary:
            raise RuntimeError(
                f"Cannot read {path}: libarchive failed ({first_error}); install 7zz or set SEVENZIP_BIN"
            ) from first_error
        with tempfile.TemporaryDirectory(prefix="bank-panel-7z-") as directory:
            command = [binary, "x", "-y", str(path), f"-o{directory}"]
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode != 0:
                raise RuntimeError(f"7-Zip failed for {path}: {completed.stderr[-1000:]}") from first_error
            result: dict[str, pd.DataFrame] = {}
            for dbf_path in Path(directory).rglob("*"):
                if dbf_path.is_file() and dbf_path.suffix.casefold() == ".dbf":
                    result[dbf_path.name.upper()] = read_dbf_bytes(dbf_path.read_bytes(), encoding=encoding)
            if not result:
                raise RuntimeError(f"7-Zip extracted no DBF files from {path}") from first_error
            return result
