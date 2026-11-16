import { useEffect, useState } from 'react';

/**
 * Callback ref to attach to an element, and its current content width in px (0 until measured).
 * A callback ref (not useRef) so measuring starts whenever the element mounts, even after an
 * early return or loading state.
 */
export function useElementWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [el, setEl] = useState<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(el);
    return () => observer.disconnect();
  }, [el]);
  return [setEl, width];
}
