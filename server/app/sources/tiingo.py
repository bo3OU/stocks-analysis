from datetime import date, timedelta

import httpx

from app.sources.base import NotFound, Source

HISTORY_YEARS = 5


class TiingoPrices(Source):
    """Daily end-of-day prices from Tiingo's free tier (50 requests/hour, 1,000/day)."""

    name = "tiingo"
    ttl = timedelta(hours=12)

    def __init__(self, cache, client: httpx.Client, api_key: str):
        super().__init__(cache)
        self.client = client
        self.api_key = api_key

    def daily(self, ticker: str):
        return self.cached(f"daily:{ticker}", lambda: self._fetch(ticker))

    def _fetch(self, ticker: str) -> list[dict]:
        start = date.today() - timedelta(days=365 * HISTORY_YEARS)
        resp = self.client.get(
            f"https://api.tiingo.com/tiingo/daily/{ticker.lower()}/prices",
            params={"startDate": start.isoformat(), "token": self.api_key},
        )
        if resp.status_code == 404:
            raise NotFound(ticker)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            raise NotFound(ticker)
        # Adjusted values keep the line continuous across splits.
        return [
            {
                "date": row["date"][:10],
                "open": row["adjOpen"],
                "high": row["adjHigh"],
                "low": row["adjLow"],
                "close": row["adjClose"],
                "volume": int(row["adjVolume"]),
            }
            for row in rows
        ]
