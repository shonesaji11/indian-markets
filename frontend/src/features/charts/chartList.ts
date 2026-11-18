import { useNavigate } from 'react-router-dom';
import { loadSetting, saveSetting } from '@/lib/storage';

/** One stock in the list the chart page shows beside the chart. */
export interface ChartListItem {
  instrument_id: number;
  symbol: string;
  /** Day's change (fraction) on the list's date. */
  change: number | null;
  /** Last close, shown when set (watchlists). */
  close?: number | null;
  /** Short note after the symbol, e.g. the date of a stock's last bar when it's behind the rest. */
  note?: string;
}

/** Where a chart was opened from: shown as the chart page's side pane, in the order you saw it. */
export interface ChartList {
  title: string;
  /** e.g. "Overview · Nifty 500 · 18 Nov 2026" */
  context?: string;
  items: ChartListItem[];
}

// Lists live in this tab's sessionStorage, keyed by a short id in the chart URL: the URL stays short
// and the list survives reloads, Back and the chart page's own URL updates. Older lists are dropped.
const KEY = 'markets.chartLists';
const KEEP = 10;

type Stored = Record<string, ChartList>;

function readAll(): Stored {
  try {
    return JSON.parse(loadSetting(KEY, true) ?? '{}') as Stored;
  } catch {
    return {};
  }
}

export function loadChartList(id: string): ChartList | null {
  return id ? (readAll()[id] ?? null) : null;
}

function storeChartList(list: ChartList): string {
  const id = Date.now().toString(36);
  const kept = Object.entries(readAll()).slice(-(KEEP - 1));
  saveSetting(KEY, JSON.stringify(Object.fromEntries([...kept, [id, list]])), true);
  return id;
}

/** Header of a list; the opener adds the items in the order they're shown. */
export type ChartListInfo = Omit<ChartList, 'items'>;

/** Market rows and scan rows both carry what the list needs. */
export const toListItems = (rows: { instrument_id: number; symbol: string; pct_change: number | null }[]): ChartListItem[] =>
  rows.map((r) => ({ instrument_id: r.instrument_id, symbol: r.symbol, change: r.pct_change }));

export const shortSymbol = (symbol: string) => symbol.replace(/-EQ$/, '');

/** Opens the daily chart; with a list, the chart page shows it alongside so you can step through it. */
export function useOpenChart() {
  const navigate = useNavigate();
  return (instrumentId: number, list?: ChartList) => {
    const listParam = list && list.items.length > 1 ? `&list=${storeChartList(list)}` : '';
    navigate(`/chart?instrument=${instrumentId}&interval=1d${listParam}`);
  };
}
