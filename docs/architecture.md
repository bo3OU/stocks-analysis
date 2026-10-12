# Architecture

Status: first slice built (ticker, price chart, SEC filings). Everything marked *planned*
is design only.

## Goals and constraints

- Personal tool, one user, US-listed companies only.
- €0/month for data. Delayed end-of-day prices are fine.
- Every number on screen says where it came from and how old it is.
- Simple to run on one machine: one Python process, one SQLite file, one web bundle.

## Shape

```
web/  React + Vite + TypeScript         one page per approved screen
  │   lightweight-charts for the chart  (Overview first)
  │ /api (JSON)
server/  FastAPI
  ├── app/main.py         routes
  ├── app/sources/        one adapter per upstream source
  ├── app/cache.py        SQLite cache shared by adapters
  ├── app/agents/         deep-dive agents            (planned)
  └── app/store/          analyses, evidence, stories (planned)
data/cache.sqlite         source cache + (later) analyses
```

Stack choice: Python because the data work (EDGAR parsing, scraping) and the agent SDKs
are strongest there; React because the chart and the evidence views are interactive.
This is a default, not yet confirmed by Ali; swapping the web side later is cheap
because the API is plain JSON.

## Source adapters and caching

Each upstream source is one class in `server/app/sources/` that subclasses `Source`:

- It owns one cache namespace (`name`) and one freshness window (`ttl`).
- It exposes typed methods (`daily(ticker)`, `submissions(cik)`) and calls
  `self.cached(key, fetch)`; it never touches the cache directly.
- `cached()` returns the stored payload while it is younger than the TTL, otherwise
  fetches and stores. If the fetch fails and an older copy exists, the old copy is served
  and the response's `freshness.fetched_at` shows its real age. `NotFound` is never
  hidden by the cache.
- Every API response carries `freshness: {source, fetched_at}` so the UI can show
  "Data as of … · N days old", as the wireframes require.

The cache is one SQLite table `source_cache(source, key, fetched_at, payload JSON)`.
Payloads are stored already normalised to our shape, so a change to our models means
bumping the key, not migrating.

| Source | Adapter | TTL | Limits we respect | Status |
|---|---|---|---|---|
| Tiingo daily prices | `tiingo.py` | 12 h | 50 req/h, 1,000/day; free tier is personal use only | built, used when `TIINGO_API_KEY` is set |
| Yahoo chart (the endpoint yfinance calls) | `yahoo.py` | 12 h | unofficial, against ToS; personal use, cached | built, default and fallback |
| SEC EDGAR tickers + submissions | `edgar.py` | 7 d / 12 h | User-Agent with contact, < 10 req/s | built |
| SEC XBRL companyfacts (fundamentals) | `edgar.py` | 1 d | same | planned |
| Finviz quote page (targets, short float, ratios, news) | `finviz.py` | 1 d, once per company per day | scrape, gray area, personal use | planned |
| yfinance data (analysts, holders) | `yahoo.py` | 1 d | as above | planned |
| GDELT, ATS job boards, USAspending/SAM, CourtListener, FEC, openFDA… | one each | 1 d | per source, see the data sources map | planned |

Price sources are an ordered list: Tiingo first when configured, then Yahoo. If all
return `NotFound` the API answers 404; if any failed for another reason, 502.

EDGAR's `submissions` file holds the latest 1,000 filings, which covers 5 years for most
companies. Very active filers (many Form 4s) will need the older pages listed in
`filings.files`; that is a small addition to `edgar.py`.

Outbound rate limiting is implicit today (one user, cached). When agents start fanning
out, each adapter gets a token bucket so parallel agents cannot break EDGAR's 10 req/s.

## Deep dive agents (planned)

The Deep dive screen launches all agents at once and shows each one's progress. Agents
read through adapters (never the network directly), so every fact they produce has a
source URL and a date.

| Agent | Gathers | Main sources |
|---|---|---|
| Filings | 8-K events, risk factor changes, auditor and legal items | EDGAR |
| Financials | Revenue, margins, cash, dilution trends | XBRL companyfacts |
| People | Execs and board, pay, insider trades, other boards, online presence | DEF 14A, Form 4, FEC, X, podcasts, web search |
| Market | Analyst targets, short interest, ownership | Finviz, yfinance, FINRA, 13F |
| News | Headlines, tone, spikes | GDELT, newswire RSS, Tiingo news |
| Hiring | Open roles over time, new areas, freezes | Greenhouse, Lever, Ashby, careers pages |
| Contracts | Government and disclosed private contracts | USAspending, SAM, 8-K item 1.01 |
| Legal and regulatory | Lawsuits, recalls, enforcement | CourtListener, SEC litigation, openFDA, NHTSA |

Then two steps run on everything collected:

1. **Analyse** cross-checks evidence and finds red flags (for example an exec departure
   and an auditor change in one quarter, a hiring freeze while guidance is raised,
   say-vs-do gaps).
2. **Story** writes the short story: what's good, what's bad, what to watch.

Each agent is a Claude call with tools that wrap our adapters, and returns a list of
**evidence items**: `{date, title, summary, tags, source, url, agent}`. Agents run as
asyncio tasks in the server; progress is written to the store and the page follows it
with server-sent events.

Open decision for Ali: how the agents pay for Claude. Options are the Claude API (pay
per use, so not €0) or running the deep dive through Claude Code on an existing
subscription. The agent code is the same either way; only the runner differs.

## Storing dated analyses (planned)

Same SQLite file, new tables:

```
analyses(id, ticker, started_at, finished_at, status, data_as_of)
agent_runs(id, analysis_id, agent, status, started_at, finished_at, error)
evidence(id, analysis_id, agent, date, title, summary, tags JSON, source, url)
stories(analysis_id, story, good JSON, bad JSON, watch JSON)
```

An analysis is never changed after it finishes. Re-run creates a new one, so the Past
analyses list shows each run with its date, age and a stale flag (older than 30 days, or
new filings since `data_as_of`). Evidence rows feed the Overview lanes, the Evidence tag
list, the People page and the red flags.

## API

Built:

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | which price sources are active |
| GET | `/api/companies/{ticker}` | `{ticker, cik, name}` from EDGAR |
| GET | `/api/companies/{ticker}/prices` | `{bars[], freshness}`: daily OHLCV, 5 years |
| GET | `/api/companies/{ticker}/filings` | `{company, filings[], freshness}` with a lane `category` per filing |

Planned:

| Method | Path | Returns |
|---|---|---|
| POST | `/api/companies/{ticker}/analyses` | starts a deep dive, returns its id |
| GET | `/api/companies/{ticker}/analyses` | past analyses with dates and stale flag |
| GET | `/api/analyses/{id}` | status per agent, then story and red flags |
| GET | `/api/analyses/{id}/events` | server-sent progress events |
| GET | `/api/analyses/{id}/evidence?tag=` | evidence for the Evidence page and chart lanes |
| GET | `/api/companies/{ticker}/people` | people with pay, trades, boards, online presence |
| GET | `/api/companies/{ticker}/snapshot` | Finviz and yfinance ratios, targets, short float |

Tickers are upper-cased and `.` becomes `-` (`BRK.B` → `BRK-B`), matching EDGAR and Yahoo.

## Next slices

1. Overview header and more lanes from free sources: XBRL fundamentals, Finviz snapshot.
2. Deep dive skeleton: analyses tables, agent runner with two agents (Filings, People),
   progress on the Deep dive screen.
3. Remaining agents, Analyse and Story steps, Evidence and People pages.
