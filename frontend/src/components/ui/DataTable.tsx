import { useMemo, useState, type ReactNode } from 'react';
import type { UrlCodec } from '@/hooks/useUrlState';

export interface SortState {
  key: string;
  desc?: boolean;
}

/** `close` / `-close` (descending) <-> SortState, for keeping a table's sort in the URL. */
export const sortCodec: UrlCodec<SortState> = {
  parse: (raw) => (raw.startsWith('-') ? { key: raw.slice(1), desc: true } : { key: raw }),
  format: (s) => `${s.desc ? '-' : ''}${s.key}`,
};

/** Stable copy of `rows` ordered by `get`; missing values always last. */
export function sortRows<T>(rows: T[], get: (row: T) => string | number | null | undefined, desc = false): T[] {
  const dir = desc ? -1 : 1;
  return [...rows].sort((a, b) => {
    const av = get(a);
    const bv = get(b);
    if (av == null) return bv == null ? 0 : 1;
    if (bv == null) return -1;
    return av < bv ? -dir : av > bv ? dir : 0;
  });
}

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Value used for sorting and default rendering. */
  value?: (row: T) => string | number | null | undefined;
  render?: (row: T) => ReactNode;
  align?: 'left' | 'right';
  sortable?: boolean;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
  initialSort?: SortState;
  /** Controlled sort (e.g. from useUrlState); when given, the table doesn't keep its own. */
  sort?: SortState;
  onSortChange?: (sort: SortState) => void;
  /** Tighter rows for compact cards. */
  dense?: boolean;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  empty = 'No data',
  initialSort,
  sort: controlledSort,
  onSortChange,
  dense,
}: DataTableProps<T>) {
  const [localSort, setLocalSort] = useState(initialSort);
  const sort = controlledSort ?? localSort;
  const setSort = onSortChange ?? setLocalSort;

  const sorted = useMemo(() => {
    const col = columns.find((c) => c.key === sort?.key);
    return col?.value ? sortRows(rows, col.value, sort?.desc) : rows;
  }, [rows, columns, sort]);

  const toggleSort = (key: string) => setSort(sort?.key === key ? { key, desc: !sort.desc } : { key });

  if (rows.length === 0) return <div className="ui-empty">{empty}</div>;

  return (
    <div className="ui-table-wrap">
      <table className={dense ? 'ui-table ui-table--dense' : 'ui-table'}>
        <thead>
          <tr>
            {columns.map((c) => {
              const sortable = c.sortable !== false && !!c.value;
              return (
                <th
                  key={c.key}
                  data-align={c.align}
                  data-sortable={sortable}
                  onClick={sortable ? () => toggleSort(c.key) : undefined}
                >
                  {c.header}
                  {sort?.key === c.key && (sort.desc ? ' ↓' : ' ↑')}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)} data-clickable={!!onRowClick} onClick={onRowClick ? () => onRowClick(row) : undefined}>
              {columns.map((c) => (
                <td key={c.key} data-align={c.align}>
                  {c.render ? c.render(row) : (c.value?.(row) ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
