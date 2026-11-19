import { useEffect, useRef, useState } from 'react';
import { useAlerts } from '@/api/queries';
import type { PriceAlert } from '@/api/types';
import { shortSymbol, useOpenChart } from '@/features/charts/chartList';
import { fmt } from '@/lib/format';
import { BellIcon } from './AlertButton';
import { alertLabel } from './alerts';
import './alerts.css';

/**
 * Bottom-right notices for alerts that fire while the app is open (any page), each until closed. Alerts that had
 * already fired when the page loaded don't pop up: they're on the Alerts page (and went to Telegram).
 */
export function AlertNotices() {
  const alerts = useAlerts();
  const openChart = useOpenChart();
  const seen = useRef<Set<string> | null>(null);
  const [shown, setShown] = useState<PriceAlert[]>([]);

  useEffect(() => {
    if (!alerts.data) return;
    const fired = alerts.data.alerts.filter((a) => a.triggered_at);
    if (seen.current === null) {
      seen.current = new Set(fired.map((a) => a.alert_id));
      return;
    }
    const fresh = fired.filter((a) => !seen.current!.has(a.alert_id));
    if (!fresh.length) return;
    fresh.forEach((a) => seen.current!.add(a.alert_id));
    setShown((s) => [...fresh, ...s]);
  }, [alerts.data]);

  if (!shown.length) return null;
  const dismiss = (id: string) => setShown((s) => s.filter((a) => a.alert_id !== id));
  return (
    <div className="alert-notices">
      {shown.map((a) => (
        <div key={a.alert_id} className="alert-notice" role="alert">
          <div className="alert-notice__head">
            <BellIcon />
            <strong>
              {shortSymbol(a.symbol)} {alertLabel(a).toLowerCase()}
            </strong>
            <button className="alert-notice__close" title="Close" onClick={() => dismiss(a.alert_id)}>
              ✕
            </button>
          </div>
          <div className="muted">
            {fmt.price(a.triggered_price)} at {a.triggered_at!.slice(11, 19)}
            {a.note && ` · ${a.note}`}
          </div>
          <button
            className="alert-notice__open"
            onClick={() => {
              dismiss(a.alert_id);
              openChart(a.instrument_id);
            }}
          >
            Open chart
          </button>
        </div>
      ))}
    </div>
  );
}
