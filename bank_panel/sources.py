from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from .models import CellValue, IndicatorSpec
from .normalize import parse_number
from .parsers import extract_cells, read_tabular_bytes

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Download:
    content: bytes
    url: str
    filename: str


class CBRSource:
    """Downloader for CBR reporting pages and linked individual forms.

    The CBR website has changed URLs several times. `discover_links` searches
    the selected reporting page for links whose text or URL contains the form
    number and year, making the pipeline work with both old and new layouts.
    """

    def __init__(self, base_url: str, timeout: int = 60, user_agent: str = "russian-bank-panel/0.1"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.timeout = timeout

    def get(self, url: str) -> Download:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return Download(response.content, response.url, Path(response.url.split("?", 1)[0]).name or "download.xlsx")

    def discover_links(self, year: int, form: str, page_url: str) -> list[str]:
        page = self.get(page_url)
        soup = BeautifulSoup(page.content, "html.parser")
        found: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(page.url, anchor["href"])
            text = f"{anchor.get_text(' ', strip=True)} {href}"
            if form in text and (str(year) in text or str(year - 1) in text):
                found.append(href)
        return list(dict.fromkeys(found))

    def parse_form(self, download: Download, specs: list[IndicatorSpec], form: str, report_date: str | None = None) -> dict[str, CellValue]:
        frames = read_tabular_bytes(download.content, download.filename)
        result: dict[str, CellValue] = {}
        for frame in frames:
            for name, cell in extract_cells(frame, specs, form=form, source_url=download.url, report_date=report_date).items():
                result.setdefault(name, cell)
        return result


class AnalizBankovSource:
    """Name-only resolver. It never returns numeric financial values."""

    def __init__(self, base_url: str, timeout: int = 60, user_agent: str = "russian-bank-panel/0.1"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.timeout = timeout

    def name_for_regn(self, regn_gko: str) -> tuple[str | None, str | None]:
        # Search endpoint is intentionally configurable because the site has
        # changed its route names. A failed lookup leaves name missing and is
        # reported by validation instead of silently inventing a name.
        candidates = [
            f"{self.base_url}/search/?q={regn_gko}",
            f"{self.base_url}/banks/?regn={regn_gko}",
        ]
        for url in candidates:
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
            except requests.RequestException:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(" ", strip=True)
            match = re.search(rf"(.{{0,100}}{re.escape(regn_gko)}.{{0,150}})", text)
            if match:
                fragment = re.sub(r"\s+", " ", match.group(1)).strip(" -:")
                return fragment, response.url
        return None, None
