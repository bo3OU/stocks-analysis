# Stocks analysis

A personal tool for looking at one US company in depth: a simple price chart with company
events on its timeline, and (later) agents that gather everything else about the company.

Start with [docs/architecture.md](docs/architecture.md) for how the pieces fit.

## What works today

Type a US ticker and get a 5-year daily price chart with SEC EDGAR filings marked on it.
Filings are grouped into lanes (10-K/10-Q, 8-K events, insider forms, proxy, 13D/13G,
offerings) that can be switched on and off. Clicking the chart lists the filings near that
day, with links to the documents on sec.gov.

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
