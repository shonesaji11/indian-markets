// React Query hooks: the only place components learn about endpoints.
import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useEffect, useRef } from 'react';
import { http } from './client';
import type {
  CalcDefinition,
  CalcSeries,
  CandleSeries,
  CoverageRow,
  IndicatorInfo,
  IngestRun,
  Instrument,
  Interval,
  LiveQuotes,
  AlertInput,
  AlertsResponse,
  PriceAlert,
  MarketOverview,
  MyWatchlist,
  ParamValue,
  SavedScan,
  ScanAgo,
  ScanDefinition,
  ScanField,
  ScanPerformance,
  ScanPerformanceRequest,
  ScanRequest,
  ScanRunResult,
  NearHigh,
  RankBy,
  SectorBreadth,
  SectorRotation,
  Watchlist,
  WatchlistQuote,
} from './types';

export const keys = {
  instruments: (q: string, exchange?: string) => ['instruments', q, exchange] as const,
  candles: (id: number, interval: Interval, start?: string) => ['candles', id, interval, start] as const,
  candlesRefresh: (id: number, interval: Interval) => ['candles-refresh', id, interval] as const,
  indicators: ['indicators'] as const,
  calcDefinitions: ['calc-definitions'] as const,
  calc: (id: number, interval: Interval, name: string, params: Record<string, ParamValue>) =>
    ['calc', id, interval, name, params] as const,
  coverage: ['coverage'] as const,
  ingestRuns: ['ingest-runs'] as const,
  scanFields: ['scan-fields'] as const,
  scanRun: (req: ScanRequest) => ['scan-run', req] as const,
  scanPerformance: (req: ScanPerformanceRequest | undefined) => ['scan-performance', req] as const,
  savedScans: ['saved-scans'] as const,
  myWatchlists: ['my-watchlists'] as const,
  watchlistQuotes: (id: string) => ['watchlist-quotes', id] as const,
  live: (ids: number[]) => ['live', ids] as const,
  alerts: ['alerts'] as const,
};

/**
 * All price alerts. Polls every 5 s while the live feed is up or the market is open (fired alerts show up and
 * the in-app notice appears), every minute otherwise.
 */
export function useAlerts() {
  return useQuery({
    queryKey: keys.alerts,
    queryFn: () => http.get<AlertsResponse>('/alerts'),
    refetchInterval: (query) => {
      const live = query.state.data?.live;
      return live && (live.connected || live.session_open) ? 5000 : 60_000;
    },
  });
}

function useAlertMutation<V, R>(mutationFn: (vars: V) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({ mutationFn, onSuccess: () => client.invalidateQueries({ queryKey: keys.alerts }) });
}

export const useCreateAlert = () =>
  useAlertMutation((input: AlertInput & { instrument_id: number }) => http.post<PriceAlert>('/alerts', input));

export const useUpdateAlert = () =>
  useAlertMutation(({ id, ...input }: AlertInput & { id: string }) => http.patch<PriceAlert>(`/alerts/${id}`, input));

export const useDeleteAlert = () => useAlertMutation((id: string) => http.delete<{ deleted: string }>(`/alerts/${id}`));

/**
 * Streamed quotes for these instruments (asking also streams them for the day). Polls every second while
 * the feed is up or the market is open, every 30 s otherwise; pauses in background tabs.
 */
export function useLiveQuotes(instrumentIds: number[], enabled = true) {
  const ids = [...new Set(instrumentIds)].sort((a, b) => a - b);
  return useQuery({
    queryKey: keys.live(ids),
    queryFn: () => http.get<LiveQuotes>('/live/quotes', { ids }),
    enabled: enabled && ids.length > 0,
    placeholderData: keepPreviousData,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && (status.connected || status.session_open) ? 1000 : 30_000;
    },
  });
}

export function useInstrumentSearch(q: string, exchange?: string) {
  return useQuery({
    queryKey: keys.instruments(q, exchange),
    queryFn: () => http.get<Instrument[]>('/instruments', { q, exchange, limit: 25 }),
    enabled: q.trim().length > 0,
    placeholderData: keepPreviousData,
  });
}

/** All stored candles, or only those from `start` (ISO date) onwards. */
export function useCandles(instrumentId: number | undefined, interval: Interval, start?: string) {
  return useQuery({
    queryKey: keys.candles(instrumentId ?? -1, interval, start),
    queryFn: () => http.get<CandleSeries>(`/candles/${instrumentId}`, { interval, start }),
    enabled: instrumentId !== undefined,
  });
}

/**
 * Downloads what a chart is missing (from its last stored bar up to now) once per visit, then reloads its
 * candles and indicators. Leaving the chart forgets the visit, so coming back downloads again. Failures
 * aren't retried by themselves (`refetch` = Retry), so they can't use up the download allowance.
 */
export function useRefreshCandles(instrumentId: number | undefined, interval: Interval, enabled: boolean) {
  const client = useQueryClient();
  return useQuery({
    queryKey: keys.candlesRefresh(instrumentId ?? -1, interval),
    queryFn: async () => {
      const res = await http.post<{ rows: number }>(`/candles/${instrumentId}/refresh?interval=${interval}`);
      if (res.rows > 0) {
        await Promise.all([
          client.invalidateQueries({ queryKey: ['candles', instrumentId, interval] }),
          client.invalidateQueries({ queryKey: ['calc', instrumentId, interval] }),
        ]);
      }
      return res;
    },
    enabled: enabled && instrumentId !== undefined,
    staleTime: Infinity,
    gcTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useIndicators() {
  return useQuery({
    queryKey: keys.indicators,
    queryFn: () => http.get<IndicatorInfo[]>('/calcs/indicators'),
    staleTime: Infinity,
  });
}

export function useCalcDefinitions() {
  return useQuery({ queryKey: keys.calcDefinitions, queryFn: () => http.get<CalcDefinition[]>('/calcs/definitions') });
}

/** Computes (and stores) an indicator on the backend, then returns its series. */
export function calcSeriesQuery(
  instrumentId: number | undefined,
  interval: Interval,
  name: string,
  params: Record<string, ParamValue>,
) {
  return queryOptions({
    queryKey: keys.calc(instrumentId ?? -1, interval, name, params),
    queryFn: () => http.post<CalcSeries>('/calcs/run', { instrument_id: instrumentId, interval, name, params }),
    enabled: instrumentId !== undefined,
    staleTime: 60_000,
  });
}

export function useCalcSeries(...args: Parameters<typeof calcSeriesQuery>) {
  return useQuery(calcSeriesQuery(...args));
}

/** Several indicators at once, e.g. every overlay on a chart. */
export function useCalcSeriesList(
  instrumentId: number | undefined,
  interval: Interval,
  selections: { name: string; params: Record<string, ParamValue> }[],
) {
  return useQueries({ queries: selections.map((s) => calcSeriesQuery(instrumentId, interval, s.name, s.params)) });
}

export function useCoverage() {
  return useQuery({ queryKey: keys.coverage, queryFn: () => http.get<CoverageRow[]>('/coverage') });
}

export function useIngestRuns() {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: keys.ingestRuns,
    queryFn: () => http.get<IngestRun[]>('/ingest/runs', { limit: 50 }),
    // Poll while anything is still running.
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === 'running') ? 1500 : false),
  });

  // When the last running ingestion finishes, data that depends on candles is stale.
  const running = query.data?.filter((r) => r.status === 'running').length ?? 0;
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current > 0 && running === 0) {
      client.invalidateQueries({ queryKey: keys.coverage });
      client.invalidateQueries({ queryKey: ['candles'] });
      client.invalidateQueries({ queryKey: ['calc'] });
      client.invalidateQueries({ queryKey: ['scan-run'] });
    }
    wasRunning.current = running;
  }, [running, client]);

  return query;
}

export interface IngestRequest {
  instrument_ids: number[];
  interval: Interval;
  start?: string;
  end?: string;
}

export function useIngest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: IngestRequest) => http.post<{ queued: number }>('/ingest', body),
    // Picks up the new 'running' rows; useIngestRuns refreshes everything else when they finish.
    onSuccess: () => client.invalidateQueries({ queryKey: keys.ingestRuns }),
  });
}

export function useSyncInstruments() {
  return useMutation({ mutationFn: () => http.post<{ instruments: number }>('/instruments/sync') });
}

export function useMarketOverview(universe: string, asOf?: string) {
  return useQuery({
    queryKey: ['market-overview', universe, asOf] as const,
    queryFn: () => http.get<MarketOverview>('/market/overview', { universe, as_of: asOf, limit: 10 }),
    placeholderData: keepPreviousData,
  });
}

export function useWatchlists() {
  return useQuery({ queryKey: ['watchlists'] as const, queryFn: () => http.get<Watchlist[]>('/watchlists') });
}

/** Your own lists (not the NSE universes), by name. */
export function useMyWatchlists() {
  return useQuery({ queryKey: keys.myWatchlists, queryFn: () => http.get<MyWatchlist[]>('/watchlists/mine') });
}

/** A list's stocks in the order added, with their last stored close and day change. */
export function useWatchlistQuotes(watchlistId: string | undefined) {
  return useQuery({
    queryKey: keys.watchlistQuotes(watchlistId ?? ''),
    queryFn: () => http.get<WatchlistQuote[]>(`/watchlists/mine/${watchlistId}/quotes`),
    enabled: !!watchlistId,
  });
}

/** Refreshes your lists afterwards; `quotes` also refreshes the lists' stock rows (membership changes). */
function useWatchlistMutation<V, R>(mutationFn: (vars: V) => Promise<R>, quotes = false) {
  const client = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.myWatchlists });
      if (quotes) client.invalidateQueries({ queryKey: ['watchlist-quotes'] });
    },
  });
}

export const useCreateWatchlist = () =>
  useWatchlistMutation((name: string) => http.post<MyWatchlist>('/watchlists/mine', { name }));

export const useRenameWatchlist = () =>
  useWatchlistMutation(({ id, name }: { id: string; name: string }) =>
    http.patch<{ renamed: string }>(`/watchlists/mine/${id}`, { name }),
  );

export const useDeleteWatchlist = () =>
  useWatchlistMutation((id: string) => http.delete<{ deleted: string }>(`/watchlists/mine/${id}`));

/** Put a stock in (`member: true`) or take it out of one of your lists; repeating either is a no-op. */
export const useSetWatchlistMember = () =>
  useWatchlistMutation(
    ({ id, instrumentId, member }: { id: string; instrumentId: number; member: boolean }): Promise<unknown> => {
      const path = `/watchlists/mine/${id}/members/${instrumentId}`;
      return member ? http.put<{ added: boolean }>(path) : http.delete<{ removed: boolean }>(path);
    },
    true,
  );

export function useScanFields() {
  return useQuery({ queryKey: keys.scanFields, queryFn: () => http.get<ScanField[]>('/scans/fields'), staleTime: Infinity });
}

/** Runs a custom scan; re-runs whenever the request changes, keeping the last result on screen. */
export function useScanRun(req: ScanRequest) {
  return useQuery({
    queryKey: keys.scanRun(req),
    queryFn: () => http.post<ScanRunResult>('/scans/run', req),
    placeholderData: keepPreviousData,
  });
}

/** Equal-weight performance of a basket since its scan date; idle while `req` is undefined. */
export function useScanPerformance(req: ScanPerformanceRequest | undefined) {
  return useQuery({
    queryKey: keys.scanPerformance(req),
    queryFn: () => http.post<ScanPerformance>('/scans/performance', req),
    enabled: req !== undefined,
  });
}

export function useSavedScans() {
  return useQuery({ queryKey: keys.savedScans, queryFn: () => http.get<SavedScan[]>('/scans/saved') });
}

export function useSaveScan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; definition: ScanDefinition }) =>
      http.post<{ scan_id: string }>('/scans/saved', body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.savedScans }),
  });
}

export function useDeleteScan() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (scanId: string) => http.delete<{ deleted: string }>(`/scans/saved/${scanId}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.savedScans }),
  });
}

export function useSectorBreadth(universe: string, periods: number[], near: NearHigh, asOf?: string) {
  return useQuery({
    queryKey: ['sector-breadth', universe, periods, near, asOf] as const,
    queryFn: () =>
      http.get<SectorBreadth>('/market/sector-breadth', {
        universe,
        as_of: asOf,
        periods,
        near_pct: near.pct,
        near_basis: near.basis,
      }),
    placeholderData: keepPreviousData,
  });
}

/**
 * Sector rank change by share above the `period` SMA or near their high (`rankBy`); disabled until
 * `ago` is set (now isn't a comparison).
 */
export function useSectorRotation(universe: string, rankBy: RankBy, period: number, near: NearHigh,
  ago: ScanAgo | undefined, minStocks: number, asOf?: string, enabled = true) {
  return useQuery({
    queryKey: ['sector-rotation', universe, rankBy, period, near, ago, minStocks, asOf] as const,
    queryFn: () =>
      http.get<SectorRotation>('/market/sector-rotation', {
        universe,
        as_of: asOf,
        rank_by: rankBy,
        period,
        near_pct: near.pct,
        near_basis: near.basis,
        ago_n: ago?.n,
        ago_unit: ago?.unit,
        min_stocks: minStocks,
      }),
    enabled: enabled && ago !== undefined,
    placeholderData: keepPreviousData,
  });
}
