import { useMemo, useState } from 'react';
import { useAlerts, useDeleteAlert, useLiveQuotes, useUpdateAlert } from '@/api/queries';
import type { PriceAlert } from '@/api/types';
import { Badge, Button, Card, DataTable, EmptyState, ErrorMessage, PageHeader, Popover, type Column } from '@/components/ui';
import { AlertForm } from '@/features/alerts/AlertForm';
import { alertLabel, away } from '@/features/alerts/alerts';
import '@/features/alerts/alerts.css';
import { shortSymbol, toListItems, useOpenChart } from '@/features/charts/chartList';
import { quoteMap } from '@/features/live/live';
import { fmt } from '@/lib/format';

const NOTIFIED: Record<string, { label: string; className: string }> = {
  sent: { label: 'Sent', className: 'alerts-page__sent' },
  failed: { label: 'Failed', className: 'alerts-page__failed' },
  off: { label: 'Not set up', className: 'muted' },
};

/** ✎ edit (the add form, prefilled) and ✕ delete (confirm), each in a small dropdown. */
function RowActions({ alert, now }: { alert: PriceAlert; now: number | null }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const update = useUpdateAlert();
  const remove = useDeleteAlert();
  return (
    <span className="alerts-page__actions" onClick={(e) => e.stopPropagation()}>
      {!alert.triggered_at && (
        <Popover
          open={editing}
          onClose={() => setEditing(false)}
          align="right"
          fixed // the table scrolls: keep the dropdown from being clipped
          trigger={
            <Button size="sm" icon variant="ghost" title="Edit" onClick={() => setEditing(!editing)}>
              ✎
            </Button>
          }
        >
          <div className="alert-pop">
            <div className="alert-pop__title">Edit alert for {shortSymbol(alert.symbol)}</div>
            <AlertForm
              now={now}
              initial={{ direction: alert.direction, price: alert.price, note: alert.note }}
              submitLabel="Save"
              busy={update.isPending}
              error={update.error}
              onSubmit={(input) => update.mutate({ id: alert.alert_id, ...input }, { onSuccess: () => setEditing(false) })}
              onCancel={() => setEditing(false)}
            />
          </div>
        </Popover>
      )}
      <Popover
        open={confirming}
        onClose={() => setConfirming(false)}
        align="right"
        fixed // the table scrolls: keep the dropdown from being clipped
        trigger={
          <Button size="sm" icon variant="ghost" title="Delete" onClick={() => setConfirming(!confirming)}>
            ✕
          </Button>
        }
      >
        <div className="ui-popover__section alerts-page__confirm">
          <span>Delete this alert?</span>
          <ErrorMessage error={remove.error} />
          <Button size="sm" variant="primary" loading={remove.isPending} onClick={() => remove.mutate(alert.alert_id)}>
            Delete
          </Button>
        </div>
      </Popover>
    </span>
  );
}

/** Your price alerts: active ones (with how far each level is) and the ones that fired. */
export function AlertsPage() {
  const alerts = useAlerts();
  const openChart = useOpenChart();
  const rows = alerts.data?.alerts ?? [];
  const active = rows.filter((a) => !a.triggered_at);
  const fired = rows.filter((a) => a.triggered_at);
  const live = useLiveQuotes(active.map((a) => a.instrument_id));
  const quotes = useMemo(() => quoteMap(live.data?.quotes), [live.data]);
  const today = alerts.data?.live.today;

  /** Today's live price when there is one, else the last stored close. */
  const nowOf = (a: PriceAlert) => {
    const q = quotes.get(a.instrument_id);
    return q && q.ts.slice(0, 10) === today ? q.ltp : a.close;
  };
  const when = (ts: string) => {
    const day = ts.slice(0, 10);
    const yesterday = today && new Date(new Date(`${today}T00:00:00`).getTime() - 86_400_000).toLocaleDateString('en-CA');
    return `${day === today ? 'Today' : day === yesterday ? 'Yesterday' : fmt.shortDate(ts)} ${ts.slice(11, 16)}`;
  };
  const open = (title: string) => (a: PriceAlert, shown: PriceAlert[]) => {
    const unique = shown.filter((r, i) => shown.findIndex((x) => x.instrument_id === r.instrument_id) === i);
    openChart(a.instrument_id, { title, items: toListItems(unique.map((r) => ({ ...r, pct_change: null }))) });
  };

  const stock: Column<PriceAlert> = { key: 'symbol', header: 'Stock', value: (a) => shortSymbol(a.symbol) };
  const level: Column<PriceAlert> = { key: 'level', header: 'Alert', value: (a) => a.price, render: alertLabel };
  const actionsCol = (a: PriceAlert) => <RowActions alert={a} now={nowOf(a)} />;
  const activeColumns: Column<PriceAlert>[] = [
    stock,
    level,
    { key: 'now', header: 'Now', align: 'right', value: (a) => nowOf(a), render: (a) => fmt.price(nowOf(a)) },
    {
      key: 'away',
      header: 'Away',
      align: 'right',
      value: (a) => away(a.price, nowOf(a)),
      render: (a) => {
        const d = away(a.price, nowOf(a));
        return d == null ? '' : fmt.pctAbs(d);
      },
    },
    { key: 'note', header: 'Note', value: (a) => a.note ?? '', render: (a) => <span className="muted">{a.note}</span> },
    { key: 'actions', header: '', sortable: false, render: actionsCol },
  ];
  const firedColumns: Column<PriceAlert>[] = [
    stock,
    level,
    {
      key: 'fired',
      header: 'Fired',
      value: (a) => a.triggered_at,
      render: (a) => `${when(a.triggered_at!)} at ${fmt.price(a.triggered_price)}`,
    },
    {
      key: 'telegram',
      header: 'Telegram',
      value: (a) => a.notified ?? '',
      render: (a) => {
        const n = a.notified ? NOTIFIED[a.notified] : { label: 'Sending…', className: 'muted' };
        return (
          <span className={n.className} title={a.notify_error ?? undefined}>
            {n.label}
          </span>
        );
      },
    },
    { key: 'actions', header: '', sortable: false, render: actionsCol },
  ];

  const status = alerts.data?.live;
  return (
    <div className="page">
      <PageHeader
        title="Alerts"
        subtitle="Each alert fires once, when the live price reaches its level."
        actions={
          <>
            {status?.session_open && !status.connected && status.lost_at && (
              <Badge tone="warn">Live feed lost at {status.lost_at.slice(11, 19)} · alerts aren't being checked</Badge>
            )}
            {alerts.data && !alerts.data.telegram && <Badge tone="warn">Telegram not set up: alerts show here only</Badge>}
          </>
        }
      />
      <ErrorMessage error={alerts.error} />
      {alerts.data && rows.length === 0 ? (
        <EmptyState>No alerts yet. Add one with the bell on a chart or a watchlist row.</EmptyState>
      ) : (
        <>
          <Card title="Active" flush>
            <DataTable
              columns={activeColumns}
              rows={active}
              rowKey={(a) => a.alert_id}
              onRowClick={open('Active alerts')}
              empty="No active alerts."
              dense
            />
          </Card>
          <Card title="Triggered" flush>
            <DataTable
              columns={firedColumns}
              rows={fired}
              rowKey={(a) => a.alert_id}
              onRowClick={open('Triggered alerts')}
              empty="None yet."
              dense
            />
          </Card>
        </>
      )}
    </div>
  );
}
