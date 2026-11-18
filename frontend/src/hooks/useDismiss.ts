import { useEffect, type RefObject } from 'react';

/** While `open`, call `onDismiss` on Escape or a mouse press outside `ref` (e.g. to close a pop-up). */
export function useDismiss(ref: RefObject<HTMLElement>, open: boolean, onDismiss: () => void) {
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onDismiss();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      e.preventDefault(); // so page-level Escape handlers (e.g. the chart's range clear) skip this one
      onDismiss();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, onDismiss, ref]);
}
