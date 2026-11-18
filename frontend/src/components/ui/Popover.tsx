import { useRef, type ReactNode } from 'react';
import { useDismiss } from '@/hooks/useDismiss';

interface PopoverProps {
  /** The button that opens it; its onClick should toggle `open`. */
  trigger: ReactNode;
  open: boolean;
  onClose: () => void;
  /** Which edge of the trigger the panel lines up with. */
  align?: 'left' | 'right';
  children: ReactNode;
}

/** A small panel that drops down under its trigger. Closes on Escape or a click outside. */
export function Popover({ trigger, open, onClose, align = 'left', children }: PopoverProps) {
  const ref = useRef<HTMLSpanElement>(null);
  useDismiss(ref, open, onClose);
  return (
    <span className="ui-popover" ref={ref}>
      {trigger}
      {open && <div className={`ui-popover__panel ui-popover__panel--${align}`}>{children}</div>}
    </span>
  );
}
