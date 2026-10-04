from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup


def names_from_analizbankov(regns: list[str], base_url: str, timeout: int = 60) -> dict[str, dict[str, Any]]:
    """Resolve only display names through the site's registration search.

    The return value contains no financial values. Missing results are left for
    the caller to review rather than guessed from technical URL identifiers.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "russian-bank-panel/0.1 (academic research)"})
    result: dict[str, dict[str, Any]] = {}
    for regn in regns:
        response = session.post(
            base_url.rstrip("/") + "/bank_ajax.php",
            data={"searcht": str(regn), "f": "ListSearchBank"},
            timeout=timeout,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "cp1251"
        soup = BeautifulSoup(response.text, "html.parser")
        anchor = soup.find("a", href=re.compile(r"BankId="))
        if not anchor:
            continue
        label = re.sub(r"\s+", " ", anchor.get_text(" ", strip=True))
        # The search result appends the registration number in parentheses.
        label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
        result[str(regn)] = {"bank_name": label, "source": response.url}
    return result
