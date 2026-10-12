# Stocks analysis

A personal tool for looking at one US company in depth: a simple price chart with company
events on its timeline, and (later) agents that gather everything else about the company.

Start with [docs/architecture.md](docs/architecture.md) for how the pieces fit.

## What works today

Type a US ticker and get a 5-year daily price chart. Under its time axis, SEC EDGAR filings
sit in one row per type (10-K/10-Q, 8-K events, insider trades, proxy, 5% holders,
offerings), lined up with the chart's dates as you zoom and pan. Clicking a dot or the chart
lists the filings on that day, with links to the documents on sec.gov.

## Run it

Needs Python 3.11+ and Node 20+.

```sh
# API on http://localhost:8000
cd server
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # then put your name and email in SEC_USER_AGENT
uvicorn app.main:app --reload

# Web app on http://localhost:5173 (proxies /api to the server)
cd web
npm install
npm run dev
```

Or build the web app once (`npm run build` in `web/`) and the API serves it at
http://localhost:8000.

Prices come from Yahoo's chart endpoint unless `TIINGO_API_KEY` is set (free key at
tiingo.com), in which case Tiingo is used first and Yahoo is the fallback.

## Tests

```sh
cd server && pytest
cd web && npm run typecheck
```
