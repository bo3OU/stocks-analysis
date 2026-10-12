import re
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.cache import Cache
from app.config import Settings
from app.models import Company, FilingsResponse, Freshness, PricesResponse
from app.sources.base import NotFound, SourceError
from app.sources.edgar import Edgar
from app.sources.tiingo import TiingoPrices
from app.sources.yahoo import YahooPrices

TICKER = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")


def normalize_ticker(raw: str) -> str:
    ticker = raw.strip().upper().replace(".", "-")
    if not TICKER.match(ticker):
        raise HTTPException(400, f"'{raw}' is not a valid US ticker")
    return ticker


def create_app(settings: Settings | None = None, client: httpx.Client | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    client = client or httpx.Client(timeout=20, follow_redirects=True)
    cache = Cache(settings.data_dir / "cache.sqlite")

    edgar = Edgar(cache, client, settings.sec_user_agent)
    price_sources = [YahooPrices(cache, client)]
    if settings.tiingo_api_key:
        price_sources.insert(0, TiingoPrices(cache, client, settings.tiingo_api_key))

    app = FastAPI(title="Stocks analysis")

    @app.get("/api/health")
    def health():
        return {"ok": True, "price_sources": [s.name for s in price_sources]}

    @app.get("/api/companies/{ticker}", response_model=Company)
    def company(ticker: str):
        ticker = normalize_ticker(ticker)
        try:
            return Company(**edgar.company(ticker))
        except NotFound:
            raise HTTPException(404, f"{ticker} is not in SEC EDGAR's ticker list")
        except SourceError as exc:
            raise HTTPException(502, str(exc))

    @app.get("/api/companies/{ticker}/prices", response_model=PricesResponse)
    def prices(ticker: str):
        ticker = normalize_ticker(ticker)
        errors = []
        for source in price_sources:
            try:
                entry = source.daily(ticker)
            except (NotFound, SourceError) as exc:
                errors.append(exc)
                continue
            return PricesResponse(
                ticker=ticker,
                bars=entry.payload,
                freshness=Freshness(source=source.name, fetched_at=entry.fetched_at),
            )
        if all(isinstance(e, NotFound) for e in errors):
            raise HTTPException(404, f"No prices found for {ticker}")
        raise HTTPException(502, "; ".join(str(e) for e in errors))

    @app.get("/api/companies/{ticker}/filings", response_model=FilingsResponse)
    def filings(ticker: str):
        ticker = normalize_ticker(ticker)
        try:
            info = Company(**edgar.company(ticker))
            entry = edgar.submissions(info.cik)
        except NotFound:
            raise HTTPException(404, f"{ticker} is not in SEC EDGAR's ticker list")
        except SourceError as exc:
            raise HTTPException(502, str(exc))
        return FilingsResponse(
            company=info,
            filings=entry.payload,
            freshness=Freshness(source=edgar.name, fetched_at=entry.fetched_at),
        )

    # Serve the built web app from the same origin when it exists (npm run build).
    web_dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if web_dist.exists():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


app = create_app()
