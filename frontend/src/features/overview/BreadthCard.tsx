import type { Breadth } from '@/api/types';
import { Card, Meter, SegmentBar } from '@/components/ui';

export function BreadthCard({ breadth, universeLabel }: { breadth: Breadth | undefined; universeLabel: string }) {
  const b = breadth;
  const ratio = b && b.declines ? (b.advances / b.declines).toFixed(2) : b?.advances ? '∞' : '–';
  return (
    <Card title="Market breadth" subtitle={`${universeLabel} · ${b?.total ?? 0} stocks`}>
      {b && (
        <div className="overview-breadth">
          <div>
            <div className="overview-breadth__headline">
              <span className="overview-breadth__ratio num">{ratio}</span>
              <span className="muted">advance / decline ratio</span>
            </div>
            <SegmentBar
              segments={[
                { key: 'adv', label: 'Advances', value: b.advances, color: 'var(--up)' },
                { key: 'unch', label: 'Unchanged', value: b.unchanged, color: 'var(--neutral-mark)' },
                { key: 'dec', label: 'Declines', value: b.declines, color: 'var(--down)' },
              ]}
            />
          </div>
          <div className="overview-breadth__meters">
            <Meter label="Above 50-day average" value={b.above_sma_50} />
            <Meter label="Above 200-day average" value={b.above_sma_200} />
          </div>
          <div className="overview-breadth__counts">
            <div>
              <span className="overview-breadth__count num">{b.new_highs}</span>
              <span className="muted">52-week highs</span>
            </div>
            <div>
              <span className="overview-breadth__count num">{b.new_lows}</span>
              <span className="muted">52-week lows</span>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
