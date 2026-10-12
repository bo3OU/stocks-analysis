import { useEffect, useRef } from "react";
import { ColorType, createChart, LineSeries, type IChartApi, type ISeriesApi } from "lightweight-charts";
import type { PriceBar } from "./api";

type Props = {
  bars: PriceBar[];
  onSelect: (date: string) => void;
  onReady: (chart: IChartApi | null) => void;
};

export default function PriceChart({ bars, onSelect, onReady }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Line"> | null>(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    const c = createChart(host.current!, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#1a1a1a",
        fontFamily: "inherit",
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: "#ece7da" } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: { horzLine: { visible: false } },
    });
    series.current = c.addSeries(LineSeries, { color: "#1a1a1a", lineWidth: 2, priceLineVisible: false });
    c.subscribeClick((param) => {
      if (typeof param.time === "string") onSelectRef.current(param.time);
    });
    chart.current = c;
    onReady(c);
    return () => {
      onReady(null);
      c.remove();
      chart.current = null;
    };
    // onReady is only read at mount; the parent keeps it stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    series.current?.setData(bars.map((b) => ({ time: b.date, value: b.close })));
    chart.current?.timeScale().fitContent();
  }, [bars]);

  return <div className="chart" ref={host} />;
}
