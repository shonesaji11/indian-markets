# Frontend map (`frontend/src/`)

React 18 + TypeScript + Vite, TanStack Query, react-router v6, lightweight-charts v5. `@/` = `src/`. Scripts: `npm run dev` (proxies `/api` → `127.0.0.1:8000`), `npm run build`, `npm run typecheck`.

## App shell and pages

| File | Contents |
|---|---|
| `main.tsx` | React root, QueryClient, router |
| `App.tsx` | `NAV` array + `<Routes>`: `/` OverviewPage, `/chart` ChartPage, `/scans` ScansPage (`/stats` redirects), `/sector?name=…` SectorPage, `/data` DataPage |
| `components/layout/AppShell.tsx` | `AppShell({title, nav, children})`, `NavItem` |
| `pages/OverviewPage.tsx` | Market overview: BenchmarkTiles, BreadthCard, SectorCard, SectorBreadthCard (row → SectorPage), ScanCards. URL: `universe`, `as_of`, `ma` (MA periods), `min` (min stocks) |
| `pages/SectorPage.tsx` | One sector's stocks (SectorStocksPanel), "All sectors" back to Overview. URL: `name`, `universe`, `as_of`, `ma`, `view` (table/charts), `page`, `sort` |
| `pages/ChartPage.tsx` | InstrumentPicker + interval + IndicatorPicker → PriceChart with calc series. URL: `instrument`, `interval`, `ind` |
| `pages/ScansPage.tsx` | Custom scans: FilterBuilder + SavedScans + ScanResultsTable (`useScanRun`, debounced, half-filled conditions pruned). URL: `f` (filter JSON), `universe`, `as_of`, `idx`, `sort`, `scan` (loaded saved id) |
| `pages/DataPage.tsx` | IngestPanel, CoverageTable, IngestRunsTable |

## Data layer (`api/`)

| File | Contents |
|---|---|
| `client.ts` | `http` (get/post/delete on `BASE = '/api'`, throws on error; array query values become repeated params) |
| `types.ts` | `INTERVALS`, `Interval`, `ParamValue`, `Instrument`, `Candle`, `CandleSeries`, `IndicatorInfo`, `CalcPoint`, `CalcSeries`, `CalcDefinition`, `CoverageRow`, `IngestRun`, `MarketRow`, `Breadth`, `ScanMetric`, `ScanResult`, `MarketOverview`, `Watchlist`; custom scans: `ScanGroup`, `ScanCondition`, `ScanOperand`, `ScanRight`, `ScanOp`, `ScanField`, `ScanDefinition`, `ScanRequest`, `ScanRunResult`, `ScanColumn`, `ScanRow`, `SavedScan`, `SectorBreadth`, `SectorBreadthRow` (mirror `backend/.../api/schemas.py` and router dicts) |
| `queries.ts` | `keys` (query keys); hooks `useInstrumentSearch`, `useCandles`, `useIndicators`, `useCalcDefinitions`, `calcSeriesQuery`/`useCalcSeries`/`useCalcSeriesList`, `useCoverage`, `useIngestRuns`, `useIngest` (+ `IngestRequest`), `useSyncInstruments`, `useMarketOverview`, `useWatchlists`, `useScanFields`, `useScanRun`, `useSavedScans`, `useSaveScan`, `useDeleteScan`, `useSectorBreadth`; `useCandles(id, interval, start?)` |

## Shared components (reuse before writing new ones)

| File | Exports |
|---|---|
| `components/ui/index.ts` | Barrel for everything below |
| `components/ui/Button.tsx` | `Button` (variant, size, icon, loading) |
| `components/ui/Card.tsx` | `Card` (title, subtitle, actions, flush, divided) |
| `components/ui/DataTable.tsx` | `DataTable<T>` + `Column<T>` (generic sortable table; sort is internal via `initialSort`, or controlled via `sort`/`onSortChange`), `SortState`, `sortCodec` (`-key` = descending), `sortRows(rows, get, desc)` (same ordering anywhere) |
| `components/ui/Feedback.tsx` | `Badge`, `EmptyState`, `ErrorMessage`, `Skeleton`, `Delta` (signed change), `Chip` |
| `components/ui/Field.tsx` | `Field`, `TextInput`, `Checkbox`, `SegmentedControl<T>`, `Select<T>`, `SelectOption` |
| `components/ui/Bars.tsx` | `Meter`, `SegmentBar`/`Segment`, `DivergingBars`/`DivergingItem` |
| `components/ui/PageHeader.tsx` | `PageHeader` |
| `components/ui/Sparkline.tsx` | `Sparkline`, `SparkPoint` |
| `components/ui/StatTile.tsx` | `StatTile` (label, value, delta, note) |
| `components/charts/PriceChart.tsx` | `PriceChart({candles, volume, series, height, showTime, compact})` (`compact` = static miniature: candles only, no axes / last-price marker / logo; caller must credit TradingView once), `toOhlc(candles)`, `OhlcPoint`, `ValuePoint`, `ChartSeries` (multi-pane lines/histograms) |

## Features (`features/<area>/`)

| File | Exports |
|---|---|
| `indicators/IndicatorPicker.tsx` | `IndicatorPicker({onAdd})`, `IndicatorSelection` |
| `indicators/ParamInputs.tsx` | `ParamInputs({defaults, params, onChange, labelled})`: one input per indicator param (used by IndicatorPicker and the scan builder) |
| `indicators/activeIndicators.ts` | `ActiveIndicator` (selection + colour slot), `addIndicator(list, sel)`, `indicatorsCodec` (URL form `sma:2:period=50,source=close;rsi:3:period=14`) |
| `indicators/toChartSeries.ts` | `SERIES_SLOTS`, `isOverlay(name)`, `paramsLabel`, `toChartSeries(calc, slot, pane, colorOf)` |
| `instruments/InstrumentPicker.tsx` | `InstrumentPicker({value, onChange, exchange, placeholder})` (debounced search) |
| `market/CoverageTable.tsx`, `IngestPanel.tsx`, `IngestRunsTable.tsx` | Data page panels |
| `scans/filterTree.ts` | `EMPTY_FILTER`, `OP_OPTIONS`, `newCondition`, `newGroup`, `prune`, `operandValue`/`operandFromValue`/`operandOptions` (select encoding `f:close`, `i:macd:signal`), `filterCodec` |
| `scans/FilterBuilder.tsx` | `FilterBuilder({value, onChange})`: recursive group editor (all/any, max depth 3), condition rows with operand + params, value or operand on the right |
| `scans/SavedScans.tsx` | `SavedScans({current, definition, onLoad})`: load / save (upsert by name) / delete |
| `scans/ScanResultsTable.tsx` | `ScanResultsTable({rows, extra, sort, onSortChange, empty})`: base columns + one per operand used; row → chart |
| `overview/BenchmarkTiles.tsx`, `BreadthCard.tsx`, `ScanCard.tsx`, `SectorCard.tsx` | Overview page cards |
| `overview/SectorBreadthCard.tsx` | Sectors ranked by % above each MA (Meter bars), MA inputs, Min stocks filter; row click → `onSelect` |
| `sectors/sectorLinks.ts` | `sectorHref(industry, ctx)`, `overviewHref(ctx)` (carry universe / as_of / MAs), `DEFAULT_MAS`, `DEFAULT_SECTOR_SORT`, `DEFAULT_UNIVERSE` |
| `sectors/SectorStocksPanel.tsx` | `StocksView` ('table' | 'charts'); one sector's stocks via `useScanRun({industry, columns: SMAs})`; Table (ScanResultsTable) or Charts (ChartGrid) |
| `charts/ChartGrid.tsx` | `GridItem` ({instrument_id, title, price, change}); `ChartGrid({items, onSelect, page, onPageChange, rows=4, months=6})`: paged grid of compact candle charts; columns = as many 240px+ tiles as fit (measured), page = columns × rows so pages are always full; fetches only the visible page; tile header shows price + change; one "Charts by TradingView" credit per grid |

## Utilities and styles

| File | Exports |
|---|---|
| `lib/format.ts` | `fmt` (`price`, `compact`, `int`, `pct` (fraction → signed %), `pctAbs`, `shortDate`, ...), `cssVar(name)` |
| `lib/time.ts` | `toChartTime(ts)`, `formatDate`, `formatDateTime`, `todayIso` |
| `hooks/useUrlState.ts` | `useUrlState(key, fallback?, codec?)`: useState stored in a query param (replace, not push; fallback omitted from URL); `UrlCodec<T>`, `boolCodec`, `intCodec`, `intListCodec`; `useUrlUpdate()` sets several params in one update (separate setters in one event overwrite each other). Use for every page filter. |
| `hooks/useElementWidth.ts` | `useElementWidth()` → `[callbackRef, width]` (ResizeObserver; works for elements that mount late) |
| `hooks/useDebouncedValue.ts` | `useDebouncedValue(value, delayMs)` |
| `hooks/useTheme.ts` | `ThemePreference`, `useThemePreference()`, `useThemeVersion()` (re-render charts on theme change) |
| `styles/tokens.css`, `global.css` | Design tokens (colours, spacing; light/dark) and base styles; per-area CSS sits next to components |
