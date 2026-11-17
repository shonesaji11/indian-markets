import httpx
import pytest

from markets.sources import nse_indices
from markets.sources.nse_indices import NseIndexSource

CSV = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "360 ONE WAM Ltd.,Financial Services,360ONE,EQ,INE466L01038\n"
    "Dummy Holding,Diversified,DUMMYHEG,EQ,INE000000000\n"
    "AXISCADES Technologies Ltd.,Capital Goods, AXISCADES ,,INE555B01013\n"
)


@pytest.mark.parametrize("index, file", [
    ("nifty500", "ind_nifty500list.csv"),
    ("niftytotalmarket", "ind_niftytotalmarket_list.csv"),  # breaks NSE's usual naming
])
def test_index_file_names(monkeypatch, index, file):
    urls = []

    def fake_get(url, **kwargs):
        urls.append(url)
        return httpx.Response(200, text=CSV, request=httpx.Request("GET", url))

    monkeypatch.setattr(nse_indices.httpx, "get", fake_get)
    rows = NseIndexSource().constituents(index)

    assert urls == [f"https://www.niftyindices.com/IndexConstituent/{file}"]
    assert [(r.symbol, r.series, r.industry) for r in rows] == [
        ("360ONE", "EQ", "Financial Services"),
        ("AXISCADES", "EQ", "Capital Goods"),  # padding stripped, blank series defaults to EQ
    ]
