import type { Category, Filing } from "./api";

// Color is used only to tell event types apart; everything else stays black on cream.
export const CATEGORIES: { id: Category; label: string; color: string }[] = [
  { id: "report", label: "10-K / 10-Q", color: "#1a1a1a" },
  { id: "event", label: "8-K events", color: "#2563eb" },
  { id: "insider", label: "Insider trades", color: "#b45309" },
  { id: "proxy", label: "Proxy", color: "#7c3aed" },
  { id: "ownership", label: "5% holders", color: "#0f766e" },
  { id: "offering", label: "Offerings", color: "#c2410c" },
  { id: "other", label: "Other", color: "#9ca3af" },
];

export const colorOf = (c: Category) => CATEGORIES.find((x) => x.id === c)!.color;

// The 8-K items worth naming on hover. Full list: sec.gov/files/form8-k.pdf
export const EIGHT_K_ITEMS: Record<string, string> = {
  "1.01": "Material agreement",
  "1.02": "Agreement terminated",
  "1.03": "Bankruptcy",
  "2.01": "Acquisition or disposal",
  "2.02": "Earnings",
  "2.03": "New debt",
  "2.05": "Restructuring costs",
  "2.06": "Impairment",
  "3.01": "Delisting notice",
  "4.01": "Auditor change",
  "4.02": "Restatement",
  "5.02": "Exec or director change",
  "5.03": "Bylaws change",
  "5.07": "Shareholder vote",
  "7.01": "Reg FD disclosure",
  "8.01": "Other event",
};

export function describe(f: Filing) {
  const items = f.items.map((i) => EIGHT_K_ITEMS[i]).filter(Boolean);
  if (items.length) return items.join(", ");
  return f.description && f.description !== f.form ? f.description : "";
}
