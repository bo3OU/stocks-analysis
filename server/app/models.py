from datetime import date, datetime

from pydantic import BaseModel


class Company(BaseModel):
    ticker: str
    cik: str
    name: str


class PriceBar(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class Filing(BaseModel):
    accession: str
    form: str
    category: str
    filed: date
    report_date: date | None = None
    description: str | None = None
    items: list[str] = []
    url: str


class Freshness(BaseModel):
    """Where a payload came from and when it was fetched, so the UI can show data age."""

    source: str
    fetched_at: datetime


class PricesResponse(BaseModel):
    ticker: str
    bars: list[PriceBar]
    freshness: Freshness


class FilingsResponse(BaseModel):
    company: Company
    filings: list[Filing]
    freshness: Freshness
