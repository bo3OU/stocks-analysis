from datetime import timedelta

import httpx

from app.sources.base import NotFound, Source

# Form type -> the lane it belongs to on the chart.
CATEGORIES = {
    "10-K": "report",
    "10-K/A": "report",
    "10-Q": "report",
    "10-Q/A": "report",
    "20-F": "report",
    "8-K": "event",
    "8-K/A": "event",
    "4": "insider",
    "4/A": "insider",
    "3": "insider",
    "5": "insider",
    "DEF 14A": "proxy",
    "DEFA14A": "proxy",
    "SC 13D": "ownership",
    "SC 13D/A": "ownership",
    "SC 13G": "ownership",
    "SC 13G/A": "ownership",
    "SCHEDULE 13D": "ownership",
    "SCHEDULE 13D/A": "ownership",
    "SCHEDULE 13G": "ownership",
    "SCHEDULE 13G/A": "ownership",
    "S-1": "offering",
    "S-3": "offering",
    "S-3ASR": "offering",
    "424B2": "offering",
    "424B3": "offering",
    "424B4": "offering",
    "424B5": "offering",
}


def categorize(form: str) -> str:
    return CATEGORIES.get(form, "other")


class Edgar(Source):
    """SEC EDGAR: free, no key. Needs a User-Agent with contact info and < 10 req/s."""

    name = "edgar"
    ttl = timedelta(hours=12)

    def __init__(self, cache, client: httpx.Client, user_agent: str):
        super().__init__(cache)
        self.client = client
        self.headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}

    def company(self, ticker: str) -> dict:
        tickers = self.cached("company_tickers", self._fetch_tickers, ttl=timedelta(days=7)).payload
        match = tickers.get(ticker.upper())
        if match is None:
            raise NotFound(ticker)
        return match

    def submissions(self, cik: str):
        return self.cached(f"submissions:{cik}", lambda: self._fetch_submissions(cik))

    def _fetch_tickers(self) -> dict:
        resp = self.client.get("https://www.sec.gov/files/company_tickers.json", headers=self.headers)
        resp.raise_for_status()
        return {
            row["ticker"].upper(): {"ticker": row["ticker"].upper(), "cik": f"{row['cik_str']:010d}", "name": row["title"]}
            for row in resp.json().values()
        }

    def _fetch_submissions(self, cik: str) -> list[dict]:
        resp = self.client.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=self.headers)
        if resp.status_code == 404:
            raise NotFound(cik)
        resp.raise_for_status()
        # "recent" holds the latest 1,000 filings, enough for the 5-year chart.
        # Older pages are listed in filings.files and can be added when needed.
        recent = resp.json()["filings"]["recent"]
        cik_int = int(cik)
        filings = []
        for i, accession in enumerate(recent["accessionNumber"]):
            form = recent["form"][i]
            doc = recent["primaryDocument"][i]
            items = recent.get("items", [""] * len(recent["form"]))[i]
            filings.append(
                {
                    "accession": accession,
                    "form": form,
                    "category": categorize(form),
                    "filed": recent["filingDate"][i],
                    "report_date": recent["reportDate"][i] or None,
                    "description": recent["primaryDocDescription"][i] or None,
                    "items": [x for x in items.split(",") if x] if items else [],
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession.replace('-', '')}/{doc}",
                }
            )
        return filings
