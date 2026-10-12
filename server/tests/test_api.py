import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests import fixtures


class Upstream:
    """Fake internet: routes requests to fixtures and counts calls per host."""

    def __init__(self, tiingo_status=200, yahoo_status=200):
        self.calls: list[str] = []
        self.tiingo_status = tiingo_status
        self.yahoo_status = yahoo_status
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request.url.host)
        if self.down:
            raise httpx.ConnectError("offline", request=request)
        url = str(request.url)
        if url == "https://www.sec.gov/files/company_tickers.json":
            assert "contact" in request.headers["user-agent"]
            return httpx.Response(200, json=fixtures.COMPANY_TICKERS)
        if url == "https://data.sec.gov/submissions/CIK0000320193.json":
            return httpx.Response(200, json=fixtures.SUBMISSIONS_AAPL)
        if request.url.host == "api.tiingo.com":
            if self.tiingo_status != 200:
                return httpx.Response(self.tiingo_status, json={"detail": "error"})
            return httpx.Response(200, json=fixtures.TIINGO_AAPL)
        if request.url.host == "query1.finance.yahoo.com":
            if "/AAPL" not in url:
                return httpx.Response(404, json=fixtures.YAHOO_NOT_FOUND)
            return httpx.Response(self.yahoo_status, json=fixtures.YAHOO_AAPL)
        return httpx.Response(404)


def make_client(tmp_path, upstream, tiingo_key=None):
    settings = Settings(sec_user_agent="test contact@example.com", tiingo_api_key=tiingo_key, data_dir=tmp_path)
    http = httpx.Client(transport=httpx.MockTransport(upstream))
    return TestClient(create_app(settings, http))


def test_filings_are_categorized_with_links(tmp_path):
    client = make_client(tmp_path, Upstream())
    body = client.get("/api/companies/aapl/filings").json()
    assert body["company"] == {"ticker": "AAPL", "cik": "0000320193", "name": "Apple Inc."}
    assert [(f["form"], f["category"]) for f in body["filings"]] == [
        ("10-K", "report"),
        ("8-K", "event"),
        ("4", "insider"),
    ]
    eight_k = body["filings"][1]
    assert eight_k["items"] == ["2.02", "9.01"]
    assert eight_k["url"] == "https://www.sec.gov/Archives/edgar/data/320193/000032019325000073/aapl-20251030.htm"
    assert body["freshness"]["source"] == "edgar"


def test_unknown_ticker_is_404(tmp_path):
    client = make_client(tmp_path, Upstream())
    assert client.get("/api/companies/ZZZZ/filings").status_code == 404
    assert client.get("/api/companies/ZZZZ/prices").status_code == 404


def test_invalid_ticker_is_400(tmp_path):
    client = make_client(tmp_path, Upstream())
    assert client.get("/api/companies/$$$/prices").status_code == 400


def test_prices_use_tiingo_when_key_is_set(tmp_path):
    client = make_client(tmp_path, Upstream(), tiingo_key="k")
    body = client.get("/api/companies/AAPL/prices").json()
    assert body["freshness"]["source"] == "tiingo"
    assert body["bars"][0] == {"date": "2025-10-30", "open": 271.0, "high": 274.1, "low": 268.5, "close": 271.4, "volume": 69886500}


def test_prices_fall_back_to_yahoo_when_tiingo_fails(tmp_path):
    client = make_client(tmp_path, Upstream(tiingo_status=429), tiingo_key="k")
    body = client.get("/api/companies/AAPL/prices").json()
    assert body["freshness"]["source"] == "yahoo"
    # The halted day with null values is dropped.
    assert [b["date"] for b in body["bars"]] == ["2025-10-30", "2025-10-31"]


def test_cache_avoids_refetching_and_survives_outage(tmp_path):
    upstream = Upstream()
    client = make_client(tmp_path, upstream)
    client.get("/api/companies/AAPL/filings")
    calls = len(upstream.calls)
    client.get("/api/companies/AAPL/filings")
    assert len(upstream.calls) == calls

    # A new app on the same cache file with the network down still answers.
    upstream.down = True
    client = make_client(tmp_path, upstream)
    assert client.get("/api/companies/AAPL/filings").status_code == 200


def test_outage_without_cache_is_502(tmp_path):
    upstream = Upstream()
    upstream.down = True
    client = make_client(tmp_path, upstream)
    assert client.get("/api/companies/AAPL/filings").status_code == 502


@pytest.mark.parametrize("raw,expected", [("brk.b", "BRK-B"), (" aapl ", "AAPL")])
def test_ticker_normalization(raw, expected):
    from app.main import normalize_ticker

    assert normalize_ticker(raw) == expected
