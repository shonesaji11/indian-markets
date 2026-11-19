import { useState } from 'react';
import { useAlerts, useCreateAlert, useDeleteAlert } from '@/api/queries';
import { Button, Popover } from '@/components/ui';
import { shortSymbol } from '@/features/charts/chartList';
import { AlertForm } from './AlertForm';
import { activeByInstrument, alertLabel } from './alerts';
import './alerts.css';

export const BellIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0" />
  </svg>
);

interface AlertButtonProps {
  instrumentId: number;
  symbol: string;
  /** Current price: shown as the level's placeholder, and how far the level is. */
  now?: number | null;
  /** Inside a scrolling list (watchlist rows): keep the dropdown from being clipped. */
  inList?: boolean;
}

/** Bell that opens a small dropdown: add a price alert for this stock, and see or delete its active ones. */
export function AlertButton({ instrumentId, symbol, now, inList = false }: AlertButtonProps) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const alerts = useAlerts();
  const create = useCreateAlert();
  const remove = useDeleteAlert();
  const active = activeByInstrument(alerts.data?.alerts).get(instrumentId) ?? [];
  const close = () => {
    setOpen(false);
    setConfirming(null);
    create.reset();
  };

  return (
    <Popover
      open={open}
      onClose={close}
      align="right"
      fixed={inList}
      trigger={
        <Button
          size="sm"
          icon
          variant={inList ? 'ghost' : 'default'}
          aria-pressed={open}
          aria-expanded={open}
          title={`Price alerts for ${shortSymbol(symbol)}`}
          className={active.length ? 'alert-bell--on' : undefined}
          onClick={(e) => {
            e.stopPropagation(); // a list row underneath would chart the stock
            if (open) close();
            else setOpen(true);
          }}
        >
          <BellIcon />
        </Button>
      }
    >
      <div className="alert-pop" onClick={(e) => e.stopPropagation()}>
        <div className="alert-pop__title">Alert for {shortSymbol(symbol)}</div>
        <AlertForm
          now={now}
          submitLabel="Add alert"
          busy={create.isPending}
          error={create.error}
          onSubmit={(input) => create.mutate({ ...input, instrument_id: instrumentId }, { onSuccess: close })}
          onCancel={close}
        />
        {active.length > 0 && (
          <div className="ui-popover__section">
            <div className="muted alert-pop__subtitle">Active on {shortSymbol(symbol)}</div>
            {active.map((a) => (
              <div key={a.alert_id} className="alert-pop__row">
                <span>{alertLabel(a)}</span>
                {confirming === a.alert_id ? (
                  <Button size="sm" variant="primary" loading={remove.isPending} onClick={() => remove.mutate(a.alert_id)}>
                    Delete
                  </Button>
                ) : (
                  <button className="alert-pop__remove" title="Delete this alert" onClick={() => setConfirming(a.alert_id)}>
                    ✕
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Popover>
  );
}
