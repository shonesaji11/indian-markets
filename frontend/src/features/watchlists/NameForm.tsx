import { useState } from 'react';
import { Button, TextInput } from '@/components/ui';

interface NameFormProps {
  initial?: string;
  placeholder: string;
  submitLabel: string;
  /** Rejects with the server's message (e.g. a name already in use), shown under the box. */
  onSubmit: (name: string) => Promise<unknown>;
  /** Shown as a ✕ button; Escape also cancels when it's set. */
  onCancel?: () => void;
  autoFocus?: boolean;
}

/** A name box with one button: create or rename a watchlist. Enter submits. */
export function NameForm({ initial = '', placeholder, submitLabel, onSubmit, onCancel, autoFocus }: NameFormProps) {
  const [name, setName] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!name.trim()) return setError('Enter a name');
    setBusy(true);
    try {
      await onSubmit(name.trim());
      setName('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="watchlist-name"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      <div className="ui-row watchlist-name__row">
        <TextInput
          value={name}
          placeholder={placeholder}
          aria-label={placeholder}
          aria-invalid={!!error}
          autoFocus={autoFocus}
          maxLength={60}
          onChange={(e) => {
            setName(e.target.value);
            setError(null);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Escape' && onCancel) {
              e.preventDefault();
              e.stopPropagation();
              onCancel();
            }
          }}
        />
        <Button size="sm" type="submit" loading={busy}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button size="sm" icon title="Cancel (Esc)" onClick={onCancel}>
            ✕
          </Button>
        )}
      </div>
      {error && <div className="watchlist-name__error">{error}</div>}
    </form>
  );
}
