from datetime import datetime, timedelta, timezone

import httpx

from app.sources.base import NotFound, Source


class YahooPrices(Source):
    """Daily prices from Yahoo's chart endpoint, the same one yfinance uses.

    Unofficial and against Yahoo's terms; used only as the no-key fallback for a
    personal tool, and cached so each ticker is fetched at most twice a day.
    """

    name = "yahoo"
    ttl = timedelta(hours=12)

    def __init__(self, cache, client: httpx.Client):
        super().__init__(cache)
        self.client = client

    def daily(self, ticker: str):
        return self.cached(f"daily:{ticker}", lambda: self._fetch(ticker))

    def _fetch(self, ticker: str) -> list[dict]:
        resp = self.client.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            params={"range": "5y", "interval": "1d", "events": "split"},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 404:
            raise NotFound(ticker)
        resp.raise_for_status()
        result = (resp.json().get("chart", {}).get("result") or [None])[0]
        if not result or not result.get("timestamp"):
            raise NotFound(ticker)
        quote = result["indicators"]["quote"][0]
        bars = []
        for i, ts in enumerate(result["timestamp"]):
            values = [quote[k][i] for k in ("open", "high", "low", "close")]
            if any(v is None for v in values):
                continue  # Yahoo leaves holes on halted days
            day = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
            o, h, l, c = values
            bars.append({"date": day, "open": o, "high": h, "low": l, "close": c, "volume": int(quote["volume"][i] or 0)})
        return bars
