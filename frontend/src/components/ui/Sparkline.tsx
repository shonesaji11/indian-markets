import { useId, useMemo, useState, type PointerEvent } from 'react';

export interface SparkPoint {
  label: string;
  value: number;
}

interface SparklineProps {
  points: SparkPoint[];
  color: string;
  height?: number;
  formatValue?: (v: number) => string;
  /** The last point is a live, not yet stored value: dashed last segment ending in a dot. */
  liveLast?: boolean;
}

const VIEW_W = 200;

/** Tiny trend line with a soft area and a hover readout of the nearest point. */
export function Sparkline({ points, color, height = 36, formatValue = (v) => v.toFixed(2), liveLast = false }: SparklineProps) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const geom = useMemo(() => {
    if (points.length < 2) return null;
    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    const pad = 2;
    const xy = values.map((v, i) => [
      (i / (values.length - 1)) * VIEW_W,
      pad + (1 - (v - min) / span) * (height - pad * 2),
    ]);
    const segs = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`);
    const line = segs.join('');
    const solid = liveLast && segs.length > 2 ? segs.slice(0, -1).join('') : line;
    const tail = liveLast ? xy.slice(-2).map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join('') : null;
    return { xy, solid, tail, area: `${line}L${VIEW_W},${height}L0,${height}Z` };
  }, [points, height, liveLast]);

  if (!geom) return <div style={{ height }} />;

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    setHover(Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1)))));
  };

  const active = hover == null ? null : geom.xy[hover];
  return (
    <div className="ui-spark">
      <svg
        viewBox={`0 0 ${VIEW_W} ${height}`}
        height={height}
        preserveAspectRatio="none"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        role="img"
        aria-label={`Trend from ${formatValue(points[0].value)} to ${formatValue(points[points.length - 1].value)}`}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <path d={geom.area} fill={`url(#${gradientId})`} />
        <path d={geom.solid} fill="none" stroke={color} strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        {geom.tail && (
          <>
            <path d={geom.tail} fill="none" stroke={color} strokeWidth={1.5} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
            {/* A zero-length round-capped stroke: stays a circle although the SVG stretches. */}
            <path
              d={`M${geom.xy[geom.xy.length - 1].join(',')}h0`}
              stroke={color}
              strokeWidth={5}
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          </>
        )}
        {active && (
          <line x1={active[0]} x2={active[0]} y1={0} y2={height} stroke="var(--axis)" vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      {hover != null && active && (
        <div className="ui-spark__tip" style={{ left: `${(active[0] / VIEW_W) * 100}%` }}>
          {points[hover].label} · {formatValue(points[hover].value)}
        </div>
      )}
    </div>
  );
}
