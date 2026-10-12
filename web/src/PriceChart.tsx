import { useEffect, useRef } from "react";
import {
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import type { PriceBar } from "./api";

export type ChartMarker = { date: string; color: string };

type Props = {
  bars: PriceBar[];
  markers: ChartMarker[];
  selected: string | null;
  onSelect: (date: string) => void;
};

export default function PriceChart({ bars, markers, selected, onSelect }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Line"> | null>(null);
  const markerApi = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
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
    const s = c.addSeries(LineSeries, { color: "#1a1a1a", lineWidth: 2, priceLineVisible: false });
    c.subscribeClick((param) => {
      if (typeof param.time === "string") onSelectRef.current(param.time);
    });
    chart.current = c;
    series.current = s;
    markerApi.current = createSeriesMarkers(s, []);
    return () => {
      c.remove();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    series.current?.setData(bars.map((b) => ({ time: b.date, value: b.close })));
    chart.current?.timeScale().fitContent();
  }, [bars]);

  useEffect(() => {
    const list: SeriesMarker<Time>[] = markers.map((m) => ({
      time: m.date,
      position: "belowBar",
      shape: "circle",
      color: m.color,
      size: 0.6,
    }));
    if (selected) {
      list.push({ time: selected, position: "aboveBar", shape: "arrowDown", color: "#1a1a1a", size: 1 });
    }
    list.sort((a, b) => String(a.time).localeCompare(String(b.time)));
    markerApi.current?.setMarkers(list);
  }, [markers, selected]);

  return <div className="chart" ref={host} />;
}
