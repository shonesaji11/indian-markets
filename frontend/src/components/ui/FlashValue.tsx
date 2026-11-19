import { useEffect, useRef, useState, type ReactNode } from 'react';

/**
 * Wraps a number that updates in place (live prices): its background flashes green when `value` rises and
 * red when it falls, fading over 0.7 s. No flash on first render or when the value is unchanged; give the
 * component a `key` per item so switching items doesn't flash.
 */
export function FlashValue({ value, children }: { value: number | null | undefined; children: ReactNode }) {
  const previous = useRef(value);
  const [flash, setFlash] = useState<{ dir: 'up' | 'down'; n: number } | null>(null);

  useEffect(() => {
    const before = previous.current;
    previous.current = value;
    if (before == null || value == null || before === value) return;
    setFlash((f) => ({ dir: value > before ? 'up' : 'down', n: (f?.n ?? 0) + 1 }));
  }, [value]);

  // A new key restarts the CSS animation on every change, even in the same direction.
  return (
    <span key={flash?.n ?? 0} className={flash ? `ui-flash ui-flash--${flash.dir}` : 'ui-flash'}>
      {children}
    </span>
  );
}
