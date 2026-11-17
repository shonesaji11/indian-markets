"""Index constituent lists published by NSE Indices (niftyindices.com) as CSV.

e.g. https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv with columns
Company Name, Industry, Symbol, Series, ISIN Code.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

import httpx

URL = "https://www.niftyindices.com/IndexConstituent/ind_{file}.csv"
# Most files are ind_<slug>list.csv; these break the pattern.
_FILE_NAMES = {"niftytotalmarket": "niftytotalmarket_list"}
# The site rejects requests without a browser-like user agent.
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}


@dataclass(frozen=True)
class NseConstituent:
    symbol: str
    series: str
    company: str
    industry: str


class NseIndexSource:
    def constituents(self, index: str) -> list[NseConstituent]:
        """`index` is the slug used in the file name: nifty50, nifty500, niftytotalmarket, ..."""
        file = _FILE_NAMES.get(index, f"{index}list")
        resp = httpx.get(URL.format(file=file), headers=HEADERS, timeout=60, follow_redirects=True)
        resp.raise_for_status()
        rows = csv.DictReader(io.StringIO(resp.text))
        return [
            NseConstituent(
                symbol=r["Symbol"].strip(),
                series=(r.get("Series") or "EQ").strip(),
                company=(r.get("Company Name") or "").strip(),
                industry=(r.get("Industry") or "").strip(),
            )
            for r in rows
            # NSE pads some lists with placeholder rows such as DUMMYHEG.
            if r.get("Symbol") and not r["Symbol"].upper().startswith("DUMMY")
        ]
