import { useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { useDismiss } from '@/hooks/useDismiss';

interface PopoverProps {
  /** The button that opens it; its onClick should toggle `open`. */
  trigger: ReactNode;
  open: boolean;
  onClose: () => void;
  /** Which edge of the trigger the panel lines up with. */
  align?: 'left' | 'right';
  /**
   * Position the panel against the window instead of its trigger, so a scrolling box it sits in (a list's
   * rows) can't clip it. Opens upwards when there's no room below; closes on any scroll or resize.
   */
  fixed?: boolean;
  children: ReactNode;
}

const ROOM_BELOW = 320; // px a panel may need under its trigger before it opens upwards instead

/** A small panel that drops down under its trigger. Closes on Escape or a click outside. */
export function Popover({ trigger, open, onClose, align = 'left', fixed = false, children }: PopoverProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  const [place, setPlace] = useState<CSSProperties | null>(null);
  useDismiss(ref, open, onClose);

  useLayoutEffect(() => {
    if (!open || !fixed || !ref.current) {
      setPlace(null);
      return;
    }
    const r = ref.current.getBoundingClientRect();
    // Set both sides of each axis: the panel's classes also set top / left / right for the non-fixed case.
    const vertical = window.innerHeight - r.bottom < ROOM_BELOW && r.top > ROOM_BELOW
      ? { top: 'auto', bottom: window.innerHeight - r.top + 6 }
      : { top: r.bottom + 6, bottom: 'auto' };
    const horizontal = align === 'right'
      ? { left: 'auto', right: window.innerWidth - r.right }
      : { left: r.left, right: 'auto' };
    setPlace({ position: 'fixed', ...vertical, ...horizontal });
    const close = () => onCloseRef.current();
    window.addEventListener('scroll', close, true); // capture: scrolling any box (the list) moves the trigger
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open, fixed, align]);

  return (
    <span className="ui-popover" ref={ref}>
      {trigger}
      {open && (!fixed || place) && (
        <div className={`ui-popover__panel ui-popover__panel--${align}`} style={place ?? undefined}>
          {children}
        </div>
      )}
    </span>
  );
}
