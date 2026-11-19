import { useState, type FormEvent } from 'react';
import type { AlertDirection, AlertInput } from '@/api/types';
import { Button, ErrorMessage, SegmentedControl, TextInput } from '@/components/ui';
import { fmt } from '@/lib/format';
import { DIRECTIONS, away, isMet, parsePrice } from './alerts';

interface AlertFormProps {
  /** Current price, to prefill a new alert and show how far the level is. */
  now?: number | null;
  initial?: AlertInput;
  submitLabel: string;
  busy?: boolean;
  error?: unknown;
  onSubmit: (input: AlertInput) => void;
  onCancel: () => void;
}

/** Above/Below, the level and an optional note; used to add an alert and to edit one. */
export function AlertForm({ now, initial, submitLabel, busy, error, onSubmit, onCancel }: AlertFormProps) {
  const [direction, setDirection] = useState<AlertDirection>(initial?.direction ?? 'above');
  // A new alert starts empty (the current price as placeholder): prefilling it would start out "already met".
  const [priceText, setPriceText] = useState(initial ? String(initial.price) : '');
  const [note, setNote] = useState(initial?.note ?? '');
  const [invalid, setInvalid] = useState(false);
  const price = parsePrice(priceText);
  const distance = price != null ? away(price, now) : null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (price == null) {
      setInvalid(true);
      return;
    }
    onSubmit({ direction, price, note: note.trim() || null });
  };

  return (
    <form className="alert-form" onSubmit={submit}>
      <SegmentedControl aria-label="Direction" value={direction} options={DIRECTIONS} onChange={setDirection} />
      <TextInput
        className="alert-form__price"
        inputMode="decimal"
        aria-label="Price"
        aria-invalid={invalid}
        placeholder={now != null ? now.toFixed(2) : 'Price'}
        value={priceText}
        autoFocus
        onChange={(e) => {
          setPriceText(e.target.value);
          setInvalid(false);
        }}
      />
      {invalid ? (
        <div className="alert-form__error">Enter a price above 0</div>
      ) : price != null && now != null && isMet(direction, price, now) ? (
        <div className="alert-form__warn">
          Already {direction} {fmt.price(price)}: it will fire right away
        </div>
      ) : (
        now != null && (
          <div className="muted alert-form__hint">
            Now {fmt.price(now)}
            {distance != null && ` · ${fmt.pctAbs(distance)} away`}
          </div>
        )
      )}
      <TextInput placeholder="Note (optional)" aria-label="Note" maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} />
      <ErrorMessage error={error} />
      <div className="alert-form__actions">
        <Button size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="sm" variant="primary" type="submit" loading={busy}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}
