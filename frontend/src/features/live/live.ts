import { useMemo, useRef } from 'react';
import type { Candle, Interval, LiveQuote, LiveStatus } from '@/api/types';

const day = (ts: string) => ts.slice(0, 10);

export const quoteMap = (quotes: LiveQuote[] | undefined) => new Map((quotes ?? []).map((q) => [q.instrument_id, q]));

export interface LiveFigures {
  close: number;
  change: number | null;
  /** Fraction vs the previous session's close. */
  pct_change: number | null;
  ts: string;
}

/**
 * A live quote's figures when it is from a later day than the stored daily bar, else null: once the nightly
 * update stores the official bar for that day, the stored figures take over by themselves.
 */
export function liveFigures(storedTs: string | null | undefined, quote: LiveQuote | undefined): LiveFigures | null {
  if (!quote || (storedTs && day(quote.ts) <= day(storedTs))) return null;
  const change = quote.prev_close ? quote.ltp - quote.prev_close : null;
  return { close: quote.ltp, change, pct_change: change != null ? change / quote.prev_close! : null, ts: quote.ts };
}

export type LiveState = { kind: 'live' | 'last' | 'lost'; at: string } | null;

/**
 * What the live badge says. `showingLive`: some figure on screen comes from a live quote.
 * Market hours: "live" while connected, "lost" after a drop (even before any quote shows).
 * After the close: "last" while live prices are still shown (until the nightly bar is stored).
 */
export function liveState(status: LiveStatus | undefined, showingLive: boolean): LiveState {
  if (!status) return null;
  if (status.session_open && !status.connected) return status.lost_at ? { kind: 'lost', at: status.lost_at } : null;
  if (!showingLive || !status.last_tick) return null;
  return { kind: status.session_open ? 'live' : 'last', at: status.last_tick };
}

const SESSION = [9 * 60 + 15, 15 * 60 + 30]; // minutes after midnight, IST
const MINUTES: Record<Interval, number> = { '1m': 1, '3m': 3, '5m': 5, '10m': 10, '15m': 15, '30m': 30, '1h': 60, '1d': 0 };
const pad = (n: number) => String(n).padStart(2, '0');

/**
 * The forming bar for `interval` after a new quote, or null when the stored bars already cover it.
 * Daily: today's bar from the quote's own open/high/low (only while no bar for today is stored). Intraday:
 * the 09:15-aligned bar holding the quote's time; it extends the stored bar of that slot or `forming`
 * (the result of the previous call), else starts at the price. Only today's quotes, in session hours.
 */
export function nextLiveBar(
  candles: Candle[],
  quote: LiveQuote | undefined,
  interval: Interval,
  today: string | undefined,
  forming: Candle | null,
): Candle | null {
  const last = candles[candles.length - 1];
  if (!quote || !last || day(quote.ts) !== today) return null;
  const price = quote.ltp;
  if (interval === '1d') {
    if (day(quote.ts) <= day(last.ts)) return null;
    return {
      ts: `${today}T00:00:00`,
      open: quote.open ?? price,
      high: Math.max(quote.high ?? price, price),
      low: Math.min(quote.low ?? price, price),
      close: price,
      volume: quote.volume ?? 0,
    };
  }
  const minute = Number(quote.ts.slice(11, 13)) * 60 + Number(quote.ts.slice(14, 16));
  if (minute < SESSION[0] || minute >= SESSION[1]) return null;
  const start = SESSION[0] + Math.floor((minute - SESSION[0]) / MINUTES[interval]) * MINUTES[interval];
  const ts = `${today}T${pad(Math.floor(start / 60))}:${pad(start % 60)}:00`;
  if (ts < last.ts) return null;
  const base = forming?.ts === ts ? forming : last.ts === ts ? last : null;
  if (!base) return { ts, open: price, high: price, low: price, close: price, volume: 0 };
  return { ...base, high: Math.max(base.high, price), low: Math.min(base.low, price), close: price };
}

/** `nextLiveBar` kept across polls, so an intraday bar's high and low collect every price seen. */
export function useLiveBar(candles: Candle[], quote: LiveQuote | undefined, interval: Interval, today: string | undefined) {
  const forming = useRef<Candle | null>(null);
  return useMemo(() => {
    forming.current = nextLiveBar(candles, quote, interval, today, forming.current);
    return forming.current;
  }, [candles, quote, interval, today]);
}
