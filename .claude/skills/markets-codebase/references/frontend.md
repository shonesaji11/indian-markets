# Frontend map (`frontend/src/`)

React 18 + TypeScript + Vite, TanStack Query, react-router v6, lightweight-charts v5. `@/` = `src/`. Scripts: `npm run dev` (proxies `/api` → `127.0.0.1:8000`), `npm run build`, `npm run typecheck`.

## App shell and pages

| File | Contents |
|---|---|
| `main.tsx` | React root, QueryClient, router |
| `App.tsx` | `NAV` array + `<Routes>`: `/` OverviewPage, `/chart` ChartPage, `/scans` ScansPage (`/stats` redirects), `/sector?name=…` SectorPage, `/watchlists` WatchlistsPage, `/data` DataPage |
| `components/layout/AppShell.tsx` | `AppShell({title, nav, children})`, `NavItem` |
| `pages/OverviewPage.tsx` | Market overview: BenchmarkTiles, BreadthCard, SectorCard, SectorBreadthCard (row → SectorPage), ScanCards. URL: `universe`, `as_of`, `ma` (MA periods), `min` (min stocks), `sector_view` (latest/rotation), `rotation_ma` (default 50), `ago` (rotation look-back, `agoCodec`, default 1w) |
| `pages/SectorPage.tsx` | One sector's stocks (SectorStocksPanel), "All sectors" back to Overview. URL: `name`, `universe`, `as_of`, `ma`, `view` (table/charts), `page`, `sort`; from the Rotation view also `sector_view`, `rotation_ma` (the MA shown), `ago`, carried back |
| `pages/ChartPage.tsx` | Full-width toolbar (InstrumentPicker, interval, indicator chips, IndicatorPicker) → window-height PriceChart with calc series and price/date range buttons in the card header (ranges are unsaved page state, cleared on stock/interval change and by Esc), plus RelatedList beside it when opened from a list; `WatchlistStar` in the chart header; `sidePane` prop (render prop taking `SidePaneProps` from `RelatedList.tsx`) replaces the side list. URL: `instrument`, `interval`, `ind`, `list` (id of a stored ChartList) |
| `pages/WatchlistsPage.tsx` | `ChartPage` with `WatchlistPane` as its side pane. URL: `wl` (list id; unknown/missing = your first list) + the chart's params |
| `pages/ScansPage.tsx` | Custom scans: FilterBuilder + SavedScans + ScanResultsTable (`useScanRun`, debounced, half-filled conditions pruned). URL: `f` (filter JSON), `universe`, `as_of`, `until`, `idx`, `sort`, `scan` (loaded saved id). With a past `as_of`, BasketPerformance card + since columns (`until` = window end, default latest) |
| `pages/DataPage.tsx` | IngestPanel, CoverageTable, IngestRunsTable |

## Data layer (`api/`)

| File | Contents |
|---|---|
| `client.ts` | `http` (get/post/put/patch/delete on `BASE = '/api'`, throws on error; array query values become repeated params) |
| `types.ts` | `INTERVALS`, `Interval`, `ParamValue`, `Instrument`, `Candle`, `CandleSeries`, `IndicatorInfo`, `CalcPoint`, `CalcSeries`, `CalcDefinition`, `CoverageRow`, `IngestRun`, `MarketRow`, `Breadth`, `ScanMetric`, `ScanResult`, `MarketOverview`, `Watchlist`, `MyWatchlist` (your list + `member_ids` in order added), `WatchlistQuote`; custom scans: `ScanGroup`, `ScanCondition`, `ScanOperand`, `ScanRight`, `ScanOp`, `ScanField`, `ScanDefinition`, `ScanRequest`, `ScanRunResult`, `ScanColumn`, `ScanRow`, `SavedScan`, `SectorBreadth`, `SectorBreadthRow`, `SectorRotation`, `SectorRotationRow` (mirror `backend/.../api/schemas.py` and router dicts) |
| `queries.ts` | `keys` (query keys); hooks `useInstrumentSearch`, `useCandles`, `useIndicators`, `useCalcDefinitions`, `calcSeriesQuery`/`useCalcSeries`/`useCalcSeriesList`, `useCoverage`, `useIngestRuns`, `useIngest` (+ `IngestRequest`), `useSyncInstruments`, `useMarketOverview`, `useWatchlists`, your lists: `useMyWatchlists`, `useWatchlistQuotes(id)`, `useCreateWatchlist`, `useRenameWatchlist`, `useDeleteWatchlist`, `useSetWatchlistMember` (`member: true/false`); `useScanFields`, `useScanRun`, `useSavedScans`, `useSaveScan`, `useDeleteScan`, `useSectorBreadth`, `useSectorRotation` (disabled until `ago` is set); `useCandles(id, interval, start?)` |

## Shared components (reuse before writing new ones)

| File | Exports |
|---|---|
| `components/ui/index.ts` | Barrel for everything below |
| `components/ui/Button.tsx` | `Button` (variant, size, icon, loading) |
| `components/ui/Card.tsx` | `Card` (title, subtitle, actions, flush, divided) |
| `components/ui/DataTable.tsx` | `DataTable<T>` + `Column<T>` (generic sortable table; `onRowClick(row, shown)` also gets the rows in displayed order; sort is internal via `initialSort`, or controlled via `sort`/`onSortChange`), `SortState`, `sortCodec` (`-key` = descending), `sortRows(rows, get, desc)` (same ordering anywhere) |
| `components/ui/Feedback.tsx` | `Badge`, `EmptyState`, `ErrorMessage`, `Skeleton`, `Delta` (signed change), `Chip` (`colorControl` slot replaces its dot) |
| `components/ui/Popover.tsx` | `Popover({trigger, open, onClose, align})`: small panel dropping down under its trigger (closes on Esc / click outside via `useDismiss`); `.ui-popover__item` / `__section` row styles. Use for menus and quick pickers instead of a modal |
| `components/ui/SwatchPicker.tsx` | `SwatchPicker` (color dot that opens a palette; `taken` marks colors in use) |
| `components/ui/Field.tsx` | `Field`, `TextInput`, `Checkbox`, `SegmentedControl<T>`, `Select<T>`, `SelectOption` |
| `components/ui/Bars.tsx` | `Meter`, `SegmentBar`/`Segment`, `DivergingBars`/`DivergingItem` |
| `components/ui/PageHeader.tsx` | `PageHeader` |
| `components/ui/Sparkline.tsx` | `Sparkline`, `SparkPoint` |
| `components/ui/StatTile.tsx` | `StatTile` (label, value, delta, note) |
| `components/charts/PriceChart.tsx` | `PriceChart({candles, volume, series, height (px or CSS), showTime, compact, ranges, rangeTool, onRangeAdd})` (`rangeTool` set = two clicks measure a range, handed to `onRangeAdd`; own pointer click detection because the chart's click event drops a 2nd click within 500 ms) (`compact` = static miniature: candles only, no axes / last-price marker / logo; caller must credit TradingView once), `toOhlc(candles)`, `OhlcPoint`, `ValuePoint`, `ChartSeries` (multi-pane lines/histograms; `group` joins an indicator's outputs into one legend row). Non-compact charts show `ChartLegend` top-left; series have no axis title tags |
| `components/charts/ranges.ts` | `RangeKind` ('price' | 'date'), `MeasuredRange`, `RangesPrimitive` (lightweight-charts series primitive drawing range boxes + labels, `pointAt(x, y)` snaps to a bar), `rangeLabel`, `barIndex` |
| `components/charts/ChartLegend.tsx` | `ChartLegend({items})`, `LegendItem`: collapsible indicator legend over the chart's top-left (name + values at the crosshair, latest bar otherwise); open state remembered via `markets.chart.legendOpen` |
| `components/charts/LineChart.tsx` | `LineChart({lines, height, format})`, `LineSpec`: static multi-line time chart (fits all points), e.g. return paths |
| `components/charts/theme.ts` | `baseLayout(attributionLogo)`, `applyChartTheme(chart)`: shared lightweight-charts layout + token colours for every chart |

## Features (`features/<area>/`)

| File | Exports |
|---|---|
| `indicators/IndicatorPicker.tsx` | `IndicatorPicker({onAdd})`, `IndicatorSelection` |
| `indicators/ParamInputs.tsx` | `ParamInputs({defaults, params, onChange, labelled})`: one input per indicator param (used by IndicatorPicker and the scan builder) |
| `indicators/activeIndicators.ts` | `ActiveIndicator` (selection + colour slot), `addIndicator(list, sel)` (first free colour), `recolorIndicator(list, slot, to)` (swaps with the line that had `to`), `indicatorsCodec` (URL form `sma:2:period=50,source=close;rsi:3:period=14`) |
| `indicators/toChartSeries.ts` | `SERIES_SLOTS`, `isOverlay(name)`, `paramsLabel`, `toChartSeries(calc, slot, pane, colorOf)` |
| `instruments/InstrumentPicker.tsx` | `InstrumentPicker({value, onChange, exchange, placeholder})` (debounced search) |
| `market/CoverageTable.tsx`, `IngestPanel.tsx`, `IngestRunsTable.tsx` | Data page panels |
| `scans/filterTree.ts` | `EMPTY_FILTER`, `OP_OPTIONS`, `newCondition`, `newGroup`, `prune` (also drops conditions with an invalid offset), `AGO_UNITS`/`MAX_AGO_BARS`/`agoValueError`/`agoError`/`conditionError`, `agoCodec` (`1w` ↔ `{n, unit}`), `operandValue`/`operandFromValue`/`operandOptions` (select encoding `f:close`, `i:macd:signal`), `filterCodec` |
| `scans/FilterBuilder.tsx` | `FilterBuilder({value, onChange})`: recursive group editor (all/any, max depth 3), condition rows with operand + params + `AgoInput` on each operand, value or operand on the right, offset error under the row |
| `scans/AgoInput.tsx` | `AgoInput({value, onChange, nowTitle, invalid})`: number + d/w/m unit, empty or 0 = now; shared by FilterBuilder and the rotation view |
| `scans/SavedScans.tsx` | `SavedScans({current, definition, onLoad})`: load / save (upsert by name) / delete |
| `scans/BasketPerformance.tsx` | `BasketPerformance({perf, loading, error, title})` card (basket, benchmark, difference, up/down, LineChart), `performanceColumns(perf, title)` (close at end + change since start), `performanceTitle`; data via `useScanPerformance` |
| `scans/ScanResultsTable.tsx` | `ScanResultsTable({rows, extra, list, sort, onSortChange, empty, afterChange})` (`afterChange` columns go right after Change): base columns + one per operand used; row → chart with the rows (in shown order) as the side list named by `list` |
| `overview/BenchmarkTiles.tsx`, `BreadthCard.tsx`, `ScanCard.tsx`, `SectorCard.tsx` | Overview page cards; `ScanCard`'s `onSelect(row, shown)` passes its rows in displayed order (OverviewPage turns each card into a chart list) |
| `overview/SectorBreadthCard.tsx` | `SectorMode`; View switch Latest (sectors ranked by % above each MA, Meter bars, MA inputs) or Rotation (one MA + `AgoInput` "Compare with": avg rank then/now, rank change, 5-day avg share and Δ pts, from `useSectorRotation`); Min stocks filter; row click → `onSelect` |
| `sectors/sectorLinks.ts` | `sectorHref(industry, ctx)`, `overviewHref(ctx)` (carry universe / as_of / MAs, and the rotation view's MA + look-back when `ctx.rotation` is set), `DEFAULT_MAS`, `DEFAULT_ROTATION_MA` (50), `DEFAULT_ROTATION_AGO` (1w), `DEFAULT_SECTOR_SORT`, `DEFAULT_UNIVERSE`, `STOCK_UNIVERSES` (watchlists offered in the Overview and Scans universe dropdowns: nifty50, nifty500, niftytotalmarket, nse_traded) |
| `sectors/SectorStocksPanel.tsx` | `StocksView` ('table' | 'charts'); one sector's stocks via `useScanRun({industry, columns: SMAs})`; Table (ScanResultsTable) or Charts (ChartGrid); both open the chart with the sector's stocks (in the table's sort) as the side list; `universeLabel` names it |
| `charts/chartList.ts` | `ChartList`/`ChartListItem`/`ChartListInfo`, `useOpenChart()` → `(instrumentId, list?)`: opens the 1d chart and stores the list in sessionStorage under the URL's `list` id (last 10 kept); `loadChartList(id)`, `toListItems(rows)` (MarketRow/ScanRow → items), `shortSymbol`. Use this for every place that opens a chart from a list |
| `charts/RelatedList.tsx` | `RelatedList({list, current, onSelect, open, onOpenChange, toolbar, onRemove, empty})`: chart page side pane (`toolbar` replaces the title, `onRemove` adds a ✕ per row, items show `close`/`note` when set); click or ↑/↓ (J/K) steps through; collapses to a rail (remembered via `markets.chart.listOpen`); stacks under the chart below 900px |
| `charts/ChartGrid.tsx` | `GridItem` ({instrument_id, title, price, change}); `ChartGrid({items, onSelect, page, onPageChange, rows=4, months=6})`: paged grid of compact candle charts; columns = as many 240px+ tiles as fit (measured), page = columns × rows so pages are always full; fetches only the visible page; tile header shows price + change; one "Charts by TradingView" credit per grid |
| `watchlists/WatchlistStar.tsx` | `WatchlistStar({instrumentId})`: ☆/★ in the chart header; Popover with a tick per list (adds/removes) and a NameForm that creates a list with this stock |
| `watchlists/WatchlistPane.tsx` | `WatchlistPane(SidePaneProps)`: Watchlists tab side pane; list picker Popover (+ new list), ✎ rename in place, delete confirm Popover, rows via `RelatedList` (close, change, stale-bar date note, ✕ remove); charts the list's first stock when none is charted; states: loading, no lists (create box), empty list, error |
| `watchlists/NameForm.tsx` | `NameForm({initial, placeholder, submitLabel, onSubmit, onCancel})`: name box + button; shows the server's error (duplicate name) under it |

## Utilities and styles

| File | Exports |
|---|---|
| `lib/format.ts` | `fmt` (`price`, `compact`, `int`, `pct` (fraction → signed %), `pctAbs`, `shortDate`, ...), `cssVar(name)` |
| `lib/storage.ts` | `loadSetting(key, session?)`, `saveSetting(key, value, session?)`: localStorage (or sessionStorage) with try/catch |
| `lib/time.ts` | `toChartTime(ts)`, `formatDate`, `formatDateTime`, `todayIso` |
| `hooks/useUrlState.ts` | `useUrlState(key, fallback?, codec?)`: useState stored in a query param (replace, not push; fallback omitted from URL); `UrlCodec<T>`, `boolCodec`, `intCodec`, `intListCodec`; `useUrlUpdate()` sets several params in one update (separate setters in one event overwrite each other). Use for every page filter. |
| `hooks/useElementWidth.ts` | `useElementWidth()` → `[callbackRef, width]` (ResizeObserver; works for elements that mount late) |
| `hooks/useDebouncedValue.ts` | `useDebouncedValue(value, delayMs)` |
| `hooks/useDismiss.ts` | `useDismiss(ref, open, onDismiss)`: Escape (marked `defaultPrevented`) or a press outside `ref` closes a pop-up (Popover, SwatchPicker) |
| `hooks/useTheme.ts` | `ThemePreference`, `useThemePreference()`, `useThemeVersion()` (re-render charts on theme change) |
| `components/layout/layout.css` | Shell + `.page` (max 1440px); `.page--wide` for full-width pages (Chart) |
| `styles/tokens.css`, `global.css` | Design tokens (colours, spacing; light/dark) and base styles; per-area CSS sits next to components |
