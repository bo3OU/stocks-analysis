export type Freshness = { source: string; fetched_at: string };

export type Company = { ticker: string; cik: string; name: string };

export type PriceBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type Category = "report" | "event" | "insider" | "proxy" | "ownership" | "offering" | "other";

export type Filing = {
  accession: string;
  form: string;
  category: Category;
  filed: string;
  report_date: string | null;
  description: string | null;
  items: string[];
  url: string;
};

export type PricesResponse = { ticker: string; bars: PriceBar[]; freshness: Freshness };
export type FilingsResponse = { company: Company; filings: Filing[]; freshness: Freshness };

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(path);
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.detail ?? `${resp.status} ${resp.statusText}`);
  }
  return resp.json();
}

export const fetchPrices = (ticker: string) =>
  get<PricesResponse>(`/api/companies/${encodeURIComponent(ticker)}/prices`);

export const fetchFilings = (ticker: string) =>
  get<FilingsResponse>(`/api/companies/${encodeURIComponent(ticker)}/filings`);
