import { useMemo, useState, type FormEvent } from "react";
import { fetchFilings, fetchPrices, type Category, type Filing, type FilingsResponse, type Freshness, type PricesResponse } from "./api";
import { CATEGORIES, colorOf, EIGHT_K_ITEMS } from "./categories";
import PriceChart, { type ChartMarker } from "./PriceChart";

type Loaded = { prices: PricesResponse; filings: FilingsResponse };

// A filing made on a weekend or holiday is drawn on the next trading day.
function snapToTradingDay(dates: string[], day: string): string | null {
  let lo = 0;
  let hi = dates.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (dates[mid] < day) lo = mid + 1;
    else hi = mid;
  }
  return lo < dates.length ? dates[lo] : null;
}

function age(f: Freshness) {
  const fetched = new Date(f.fetched_at);
  const days = Math.floor((Date.now() - fetched.getTime()) / 86_400_000);
  const when = fetched.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  return `${when} · ${days === 0 ? "today" : `${days} day${days === 1 ? "" : "s"} old`} · ${f.source}`;
}

function describe(f: Filing) {
  const items = f.items.map((i) => EIGHT_K_ITEMS[i]).filter(Boolean);
  if (items.length) return items.join(", ");
  return f.description && f.description !== f.form ? f.description : "";
}

export default function App() {
  const [input, setInput] = useState("");
  const [data, setData] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [enabled, setEnabled] = useState<Set<Category>>(
    () => new Set(CATEGORIES.filter((c) => c.defaultOn).map((c) => c.id)),
  );

  async function load(e: FormEvent) {
    e.preventDefault();
    const ticker = input.trim();
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const [prices, filings] = await Promise.all([fetchPrices(ticker), fetchFilings(ticker)]);
      setData({ prices, filings });
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  // Each filing placed on the trading day it lands on; filings before the chart starts are left out.
  const placed = useMemo(() => {
    if (!data) return [];
    const dates = data.prices.bars.map((b) => b.date);
    const first = dates[0];
    return data.filings.filings
      .filter((f) => first && f.filed >= first)
      .map((f) => ({ filing: f, day: snapToTradingDay(dates, f.filed) ?? dates[dates.length - 1] }));
  }, [data]);

  const visible = placed.filter((p) => enabled.has(p.filing.category));

  const markers: ChartMarker[] = useMemo(() => {
    const seen = new Set<string>();
    const out: ChartMarker[] = [];
    for (const { filing, day } of visible) {
      const key = `${day}:${filing.category}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ date: day, color: colorOf(filing.category) });
    }
    return out;
  }, [visible]);

  const counts = useMemo(() => {
    const m = new Map<Category, number>();
    for (const { filing } of placed) m.set(filing.category, (m.get(filing.category) ?? 0) + 1);
    return m;
  }, [placed]);

  const panel = selected ? visible.filter((p) => p.day === selected) : visible.slice(0, 25);

  // Clicks rarely land exactly on a dot, so pick the closest day with a visible filing within three weeks.
  function selectNear(day: string) {
    const target = Date.parse(day);
    let best: string | null = null;
    let bestGap = 21 * 86_400_000;
    for (const p of visible) {
      const gap = Math.abs(Date.parse(p.day) - target);
      if (gap <= bestGap) {
        best = p.day;
        bestGap = gap;
      }
    }
    setSelected(best ?? day);
  }

  function toggle(c: Category) {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  }

  return (
    <main>
      <form className="search" onSubmit={load}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="US ticker, e.g. AAPL"
          aria-label="Ticker"
          autoFocus
        />
        <button type="submit" disabled={loading}>
          {loading ? "Loading…" : "Show"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {data && (
        <>
          <header className="company">
            <h1>
              {data.filings.company.name} <span className="muted">{data.filings.company.ticker}</span>
            </h1>
            <p className="muted small">
              Prices as of {age(data.prices.freshness)} · Filings as of {age(data.filings.freshness)}
            </p>
          </header>

          <div className="lanes">
            {CATEGORIES.filter((c) => counts.get(c.id)).map((c) => (
              <button
                key={c.id}
                className={enabled.has(c.id) ? "chip on" : "chip"}
                onClick={() => toggle(c.id)}
                type="button"
              >
                <span className="dot" style={{ background: c.color }} />
                {c.label} <span className="muted">{counts.get(c.id)}</span>
              </button>
            ))}
          </div>

          <PriceChart bars={data.prices.bars} markers={markers} selected={selected} onSelect={selectNear} />

          <section className="day">
            <h2>
              {selected ? `Filings on ${selected}` : "Latest filings"}
              {selected && (
                <button className="link" type="button" onClick={() => setSelected(null)}>
                  show latest
                </button>
              )}
            </h2>
            {panel.length === 0 && <p className="muted">No filings in the selected lanes on this day.</p>}
            <ul>
              {panel.map(({ filing }) => (
                <li key={filing.accession}>
                  <span className="dot" style={{ background: colorOf(filing.category) }} />
                  <span className="date">{filing.filed}</span>
                  <a href={filing.url} target="_blank" rel="noreferrer">
                    {filing.form}
                  </a>
                  <span className="muted">{describe(filing)}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}

      {!data && !error && <p className="muted hint">Type a ticker to see its daily price with SEC filings on the timeline.</p>}
    </main>
  );
}
