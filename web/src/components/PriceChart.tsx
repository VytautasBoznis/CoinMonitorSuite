import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  LineType,
  createChart,
  createSeriesMarkers,
  createTextWatermark,
  type AutoscaleInfo,
  type CandlestickData,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type ITextWatermarkPluginApi,
  type LineStyle as LineStyleT,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import { api, type Account, type BotState, type Candle, type Config, type TradeRow } from "../api";
import { arrow, decimals, fmtCompactUsd, fmtDur, fmtPct, fmtPx, tone } from "../format";
import type { Socket } from "../hooks";
import { Panel } from "./Panel";

const C = {
  bg: "#12161c",
  grid: "#171c23",
  line: "#222831",
  ink: "#e6e8ea",
  ink2: "#9aa4b2",
  ink3: "#5d6673",
  up: "#12b076",
  down: "#ea3943",
  accent: "#3987e5",
  gap: "rgba(93, 102, 115, 0.16)",
};
const STEP_MS: Record<string, number> = { "1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000 };
const LIQ_REFRESH_MS = 30_000;

const sec = (ms: number) => (ms / 1000) as UTCTimestamp;
const toBar = (c: Candle): CandlestickData<Time> => ({ time: sec(c.time), open: c.open, high: c.high, low: c.low, close: c.close });

type Series = {
  candles: ISeriesApi<"Candlestick">;
  trail: ISeriesApi<"Line">;
  sell: ISeriesApi<"Histogram">;
  buy: ISeriesApi<"Histogram">;
  gapHi: ISeriesApi<"Histogram">;
  gapLo: ISeriesApi<"Histogram">;
  markers: ISeriesMarkersPluginApi<Time>;
  watermark: ITextWatermarkPluginApi<Time>;
};

export function PriceChart({
  coin,
  interval,
  intervals,
  onInterval,
  socket,
  state,
  account,
  trades,
  rule,
}: {
  coin: string;
  interval: string;
  intervals: string[];
  onInterval: (i: string) => void;
  socket?: Socket;
  state?: BotState;
  account?: Account;
  trades?: TradeRow[];
  rule: Config["rule"];
}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi>(null);
  const series = useRef<Series>(null);
  const lines = useRef<IPriceLine[]>([]);
  const linePrices = useRef<number[]>([]); // kept in the autoscale range so the bid never sits off-screen
  const drop = rule.drop;
  const bars = useRef<Candle[]>([]);
  const [last, setLast] = useState<Candle>();
  const [hover, setHover] = useState<Candle>();
  const [lastClosed, setLastClosed] = useState<number>();
  const [liq, setLiq] = useState<{ coverage: number; sell: number; buy: number }>();
  const [error, setError] = useState<string>();

  // The chart and its series live for the component's lifetime; effects below feed them.
  useEffect(() => {
    const ch = createChart(el.current!, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: C.bg },
        textColor: C.ink2,
        fontFamily: "'JetBrains Mono Variable', ui-monospace, monospace",
        fontSize: 11,
        panes: { separatorColor: C.line, separatorHoverColor: "#2b323d", enableResize: true },
      },
      grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: C.ink3, style: LineStyle.Dashed, labelBackgroundColor: "#2b323d" },
        horzLine: { color: C.ink3, style: LineStyle.Dashed, labelBackgroundColor: "#2b323d" },
      },
      rightPriceScale: { borderColor: C.line },
      timeScale: { borderColor: C.line, timeVisible: true, secondsVisible: false, rightOffset: 8, barSpacing: 7 },
    });
    // Up candles hollow, down filled: direction reads without color.
    const candles = ch.addSeries(CandlestickSeries, {
      upColor: "rgba(0,0,0,0)",
      borderUpColor: C.up,
      wickUpColor: C.up,
      downColor: C.down,
      borderDownColor: C.down,
      wickDownColor: C.down,
      priceLineColor: C.ink3,
      priceLineStyle: LineStyle.Dotted,
      autoscaleInfoProvider: (original: () => AutoscaleInfo | null) => {
        const r = original();
        const extra = linePrices.current;
        if (!r?.priceRange || !extra.length) return r;
        const { minValue, maxValue } = r.priceRange;
        return { ...r, priceRange: { minValue: Math.min(minValue, ...extra), maxValue: Math.max(maxValue, ...extra) } };
      },
    });
    // Where the bot's buy order sits each minute: the prior 1m close minus the rule's drop. A wick
    // through this line is a fill.
    const trail = ch.addSeries(LineSeries, {
      color: "rgba(57, 135, 229, 0.75)",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lineType: LineType.WithSteps,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const usd = { type: "custom" as const, formatter: (v: number) => fmtCompactUsd(Math.abs(v)), minMove: 1 };
    const quiet = { priceLineVisible: false, lastValueVisible: false, priceFormat: usd };
    const gapHi = ch.addSeries(HistogramSeries, { ...quiet, color: C.gap }, 1);
    const gapLo = ch.addSeries(HistogramSeries, { ...quiet, color: C.gap }, 1);
    const sell = ch.addSeries(HistogramSeries, { ...quiet, color: C.down }, 1);
    const buy = ch.addSeries(HistogramSeries, { ...quiet, color: C.up }, 1);
    ch.panes()[1].setStretchFactor(0.34);
    createTextWatermark(ch.panes()[1], {
      horzAlign: "left",
      vertAlign: "top",
      lines: [{ text: "LIQUIDATIONS · BYBIT   ▲ shorts squeezed   ▼ longs liquidated", color: "rgba(154,164,178,0.45)", fontSize: 10 }],
    });
    const watermark = createTextWatermark(ch.panes()[0], { lines: [] });
    const markers = createSeriesMarkers(candles, []);
    ch.subscribeCrosshairMove((p) => {
      const d = p.time ? (p.seriesData.get(candles) as CandlestickData<Time> | undefined) : undefined;
      setHover(d ? { time: (p.time as number) * 1000, open: d.open, high: d.high, low: d.low, close: d.close, volume: 0 } : undefined);
    });
    chart.current = ch;
    series.current = { candles, trail, sell, buy, gapHi, gapLo, markers, watermark };
    return () => {
      ch.remove();
      chart.current = null;
      series.current = null;
    };
  }, []);

  // Snapshot of the last 500 candles whenever the coin or interval changes.
  useEffect(() => {
    const s = series.current!;
    let alive = true;
    bars.current = [];
    s.candles.setData([]);
    s.trail.setData([]);
    setLast(undefined);
    setError(undefined);
    s.watermark.applyOptions({
      horzAlign: "center",
      vertAlign: "center",
      lines: [
        { text: `${coin}-PERP`, color: "rgba(154,164,178,0.06)", fontSize: 72, fontStyle: "700" },
        { text: interval, color: "rgba(154,164,178,0.06)", fontSize: 28, fontStyle: "600" },
      ],
    });
    api
      .candles(coin, interval)
      .then((cs) => {
        if (!alive || !cs.length) return;
        bars.current = cs;
        const d = decimals(cs[cs.length - 1].close);
        s.candles.applyOptions({ priceFormat: { type: "price", precision: d, minMove: 10 ** -d } });
        s.candles.setData(cs.map(toBar));
        if (interval === "1m") s.trail.setData(cs.slice(1).map((c, i) => ({ time: sec(c.time), value: cs[i].close * (1 - drop) })));
        setLast(cs[cs.length - 1]);
        setLastClosed(cs.length > 1 ? cs[cs.length - 2].close : undefined);
        chart.current!.timeScale().setVisibleLogicalRange({ from: cs.length - 160, to: cs.length + 8 });
      })
      .catch((e) => alive && setError(e.message));
    return () => {
      alive = false;
    };
  }, [coin, interval, drop]);

  // Live candle from the venue websocket.
  useEffect(() => {
    if (!socket) return;
    const off = socket.listen((m) => {
      if (m.channel !== "candle" || m.data.s !== coin || m.data.i !== interval) return;
      const d = m.data;
      const c: Candle = { time: d.t, open: +d.o, high: +d.h, low: +d.l, close: +d.c, volume: +d.v };
      const prev = bars.current[bars.current.length - 1];
      if (!prev || c.time < prev.time) return; // before the snapshot, or stale
      if (c.time > prev.time) {
        bars.current = [...bars.current, c];
        setLastClosed(prev.close);
        if (interval === "1m") series.current?.trail.update({ time: sec(c.time), value: prev.close * (1 - drop) });
      } else bars.current[bars.current.length - 1] = c;
      series.current?.candles.update(toBar(c));
      setLast(c);
    });
    const unsub = socket.subscribe(`candle:${coin}:${interval}`, { type: "candle", coin, interval });
    return () => {
      off();
      unsub();
    };
  }, [socket, coin, interval, drop]);

  // Liquidation pane: per-bucket forced flow, and grey bands where the collector saw nothing.
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const step = STEP_MS[interval];
    const load = async () => {
      const end = Date.now();
      const start = bars.current[0]?.time ?? end - 500 * step;
      try {
        const l = await api.liquidations(coin, interval, start, end);
        const s = series.current;
        if (!alive || !s) return;
        s.sell.setData(l.buckets.filter((b) => b.sell > 0).map((b) => ({ time: sec(b.time), value: -b.sell })));
        s.buy.setData(l.buckets.filter((b) => b.buy > 0).map((b) => ({ time: sec(b.time), value: b.buy })));
        const peak = l.buckets.reduce((m, b) => Math.max(m, b.sell, b.buy), 1);
        const gapTimes: number[] = [];
        for (const [a, b] of l.gaps) for (let t = Math.ceil(a / step) * step; t < b; t += step) gapTimes.push(t);
        s.gapHi.setData(gapTimes.map((t) => ({ time: sec(t), value: peak })));
        s.gapLo.setData(gapTimes.map((t) => ({ time: sec(t), value: -peak })));
        setLiq({
          coverage: l.coverage,
          sell: l.buckets.reduce((m, b) => m + b.sell, 0),
          buy: l.buckets.reduce((m, b) => m + b.buy, 0),
        });
      } catch {
        if (alive) setLiq(undefined);
      } finally {
        if (alive) timer = window.setTimeout(load, LIQ_REFRESH_MS);
      }
    };
    load();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [coin, interval]);

  // The bot on the chart: resting bid, take-profit, position and its liquidation price as lines.
  useEffect(() => {
    const s = series.current;
    if (!s) return;
    for (const l of lines.current) s.candles.removePriceLine(l);
    lines.current = [];
    linePrices.current = [];
    const add = (price: number, color: string, title: string, lineStyle: LineStyleT = LineStyle.Dashed) => {
      lines.current.push(s.candles.createPriceLine({ price, color, title, lineStyle, lineWidth: 1, axisLabelVisible: true }));
      if (title !== "LIQ") linePrices.current.push(price); // a 5x liq price would squash the candles
    };
    let busy = false;
    if (account?.configured) {
      for (const o of account.orders.filter((o) => o.coin === coin)) {
        if (o.side === "B" && !o.reduce_only) add(o.px, C.accent, "BID");
        else if (o.reduce_only) add(o.px, C.up, "TP");
        busy = true;
      }
      const p = account.positions.find((p) => p.coin === coin);
      s.trail.applyOptions({ visible: !p }); // one position per coin: no bid while holding
      if (p) {
        busy = true;
        add(p.entry_px, C.ink, `LONG ${p.szi}`, LineStyle.Solid);
        if (p.liq_px) add(p.liq_px, C.down, "LIQ", LineStyle.Dotted);
      }
    }
    // Nothing on the venue: show where the frozen rule would rest the bid right now.
    if (!busy && lastClosed && interval === "1m")
      add(lastClosed * (1 - rule.drop), C.accent, `BUY −${(rule.drop * 100).toFixed(1)}%`, LineStyle.Dotted);
  }, [account, coin, interval, lastClosed, rule]);

  // Fills and exits from the ledger, at their exact prices.
  useEffect(() => {
    const s = series.current;
    if (!s) return;
    const step = STEP_MS[interval];
    const first = bars.current[0]?.time ?? Infinity;
    const at = (ms: number) => sec(Math.floor(ms / step) * step);
    const ms: SeriesMarker<Time>[] = [];
    for (const t of trades ?? []) {
      if (t.coin !== coin || t.fill_ms < first) continue;
      ms.push({ time: at(t.fill_ms), position: "atPriceMiddle", price: t.fill_px, shape: "arrowUp", color: C.accent, text: "BUY" });
      if (t.exit_px != null && t.exit_ms != null)
        ms.push({
          time: at(t.exit_ms),
          position: "atPriceMiddle",
          price: t.exit_px,
          shape: "arrowDown",
          color: (t.net ?? 0) >= 0 ? C.up : C.down,
          text: (t.exit_reason ?? "exit").toUpperCase(),
        });
    }
    ms.sort((a, b) => (a.time as number) - (b.time as number));
    s.markers.setMarkers(ms);
  }, [trades, coin, interval, last?.time]);

  const intent = describeIntent(coin, state, account, trades, lastClosed, rule, Date.now());
  const shown = hover ?? last;
  const change = shown ? shown.close / shown.open - 1 : undefined;
  return (
    <Panel
      title={
        <span>
          {coin}-PERP <span className="text-ink-3">· hyperliquid</span>
        </span>
      }
      right={
        <div className="flex items-center gap-4">
          {liq && (
            <span className="num text-[11px] text-ink-3" title="Bybit liquidations in view; grey = collector saw nothing">
              <span className="text-down">▼ {fmtCompactUsd(liq.sell)}</span>
              <span className="mx-2 text-up">▲ {fmtCompactUsd(liq.buy)}</span>
              {(liq.coverage * 100).toFixed(0)}% covered
            </span>
          )}
          <div className="flex rounded-[4px] bg-bg p-0.5">
            {intervals.map((i) => (
              <button
                key={i}
                onClick={() => onInterval(i)}
                className={`num rounded-[3px] px-2 py-0.5 text-[11px] ${
                  i === interval ? "bg-panel-2 text-ink" : "text-ink-3 hover:text-ink-2"
                }`}
              >
                {i}
              </button>
            ))}
          </div>
        </div>
      }
    >
      <div className="relative h-full">
        <div ref={el} className="absolute inset-0" />
        <div className="num pointer-events-none absolute left-3 top-2 z-10 flex gap-3 text-[11px]">
          {shown &&
            (["open", "high", "low", "close"] as const).map((k) => (
              <span key={k} className="text-ink-3">
                {k[0].toUpperCase()} <span className={tone(change)}>{fmtPx(shown[k])}</span>
              </span>
            ))}
          {shown && (
            <span className={tone(change)}>
              {arrow(change)} {fmtPct(change)}
            </span>
          )}
        </div>
        {intent && (
          <div className="pointer-events-none absolute left-3 top-8 z-10 flex max-w-[72%] items-center gap-2.5 rounded-[4px] border border-line bg-bg/85 px-2.5 py-1.5 text-[12px] backdrop-blur-sm">
            <span
              className={`text-[10px] font-semibold uppercase tracking-[0.12em] ${
                intent.kind === "hold" ? "text-up" : intent.kind === "wait" ? "text-accent" : "text-ink-3"
              }`}
            >
              ● Intent
            </span>
            <span className="text-ink">{intent.text}</span>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 z-20 grid place-items-center text-sm text-down">chart data: {error}</div>
        )}
      </div>
    </Panel>
  );
}

type Intent = { kind: "wait" | "hold" | "off"; text: string };

/** What the bot is trying to do on this coin right now, in one plain sentence. */
function describeIntent(
  coin: string,
  state: BotState | undefined,
  account: Account | undefined,
  trades: TradeRow[] | undefined,
  lastClosed: number | undefined,
  rule: Config["rule"],
  now: number,
): Intent | undefined {
  const drop = `${(rule.drop * 100).toFixed(1)}%`;
  if (account?.configured) {
    const pos = account.positions.find((p) => p.coin === coin);
    if (pos) {
      const tp = account.orders.find((o) => o.coin === coin && o.reduce_only);
      const open = trades?.find((t) => t.coin === coin && t.exit_ms == null);
      const out = open ? `, or at market in ${fmtDur(open.fill_ms + rule.hold_ms - now)}` : "";
      return {
        kind: "hold",
        text: `Holding ${pos.szi} ${coin} bought at ${fmtPx(pos.entry_px)}. Sells at ${fmtPx(tp?.px)} (+${(rule.target * 100).toFixed(1)}%)${out}.`,
      };
    }
  }
  if (!state) return undefined;
  const level = lastClosed != null ? fmtPx(lastClosed * (1 - rule.drop)) : undefined;
  if (!state.db) return { kind: "off", text: "Control store down, so the bot places nothing new." };
  if (state.heartbeat !== "alive")
    return {
      kind: "off",
      text: `Bot not running, so nothing is bidding.${level ? ` Running, it would bid ${level} (the dashed line, ${drop} under the last 1m close).` : ""}`,
    };
  if (state.mode === "HALT") return { kind: "off", text: "Bot halted: not bidding until `coinmon bot resume`." };
  if (state.mode === "DRAIN") return { kind: "off", text: "Draining: no new bids, closing what is open." };
  const bid = account?.configured
    ? account.orders.find((o) => o.coin === coin && o.side === "B" && !o.reduce_only)
    : undefined;
  const px = bid ? fmtPx(bid.px) : level;
  return {
    kind: "wait",
    text: `Waiting to buy ${coin} at ${px ?? "…"}, ${drop} under the last 1m close. It fills only if price crashes that far inside one minute.`,
  };
}
