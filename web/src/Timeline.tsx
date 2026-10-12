import { useCallback, useEffect, useMemo, useState } from "react";
import type { IChartApi } from "lightweight-charts";
import type { Filing, PriceBar } from "./api";
import { CATEGORIES, describe } from "./categories";
import PriceChart from "./PriceChart";

export type Placed = { filing: Filing; day: string };

type Props = {
  bars: PriceBar[];
  placed: Placed[];
  selected: string | null;
  onSelect: (date: string) => void;
};

// Price line on top, then one lane per filing type underneath, sharing the chart's time axis.
export default function Timeline({ bars, placed, selected, onSelect }: Props) {
  const [chart, setChart] = useState<IChartApi | null>(null);
  const [, setTick] = useState(0);
  const onReady = useCallback((c: IChartApi | null) => setChart(c), []);

  // Lanes are plain DOM positioned from the chart's time scale, so redraw on zoom, pan and resize.
  useEffect(() => {
    if (!chart) return;
    const redraw = () => setTick((t) => t + 1);
    const ts = chart.timeScale();
    ts.subscribeVisibleLogicalRangeChange(redraw);
    ts.subscribeSizeChange(redraw);
    return () => {
      ts.unsubscribeVisibleLogicalRangeChange(redraw);
      ts.unsubscribeSizeChange(redraw);
    };
  }, [chart]);

  const lanes = useMemo(() => {
    return CATEGORIES.map((c) => {
      const byDay = new Map<string, Filing[]>();
      for (const p of placed) {
        if (p.filing.category !== c.id) continue;
        byDay.set(p.day, [...(byDay.get(p.day) ?? []), p.filing]);
      }
      return { ...c, byDay };
    }).filter((l) => l.byDay.size > 0);
  }, [placed]);

  const ts = chart?.timeScale();
  const paneWidth = ts?.width() ?? 0;
  const xOf = (day: string) => {
    const x = ts?.timeToCoordinate(day);
    return x == null || x < 0 || x > paneWidth ? null : x;
  };
  const cursorX = selected ? xOf(selected) : null;

  return (
    <div className="timeline">
      <div className="labels">
        <div className="chart-spacer" />
        {lanes.map((l) => (
          <div key={l.id} className="lane-label">
            {l.label}
          </div>
        ))}
      </div>
      <div className="tracks">
        <PriceChart bars={bars} onSelect={onSelect} onReady={onReady} />
        {lanes.map((l) => (
          <div key={l.id} className="lane" style={{ width: paneWidth || undefined }}>
            {[...l.byDay.entries()].map(([day, filings]) => {
              const x = xOf(day);
              if (x == null) return null;
              const title = `${day}: ${filings.map((f) => [f.form, describe(f)].filter(Boolean).join(" ")).join(", ")}`;
              return (
                <button
                  key={day}
                  type="button"
                  className="lane-dot"
                  style={{ left: x, background: l.color }}
                  title={title}
                  aria-label={title}
                  onClick={() => onSelect(day)}
                />
              );
            })}
          </div>
        ))}
        {cursorX != null && <div className="cursor" style={{ left: cursorX }} />}
      </div>
    </div>
  );
}
