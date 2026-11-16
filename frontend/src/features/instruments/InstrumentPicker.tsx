import { useState } from 'react';
import { useInstrumentSearch } from '@/api/queries';
import type { Instrument } from '@/api/types';
import { TextInput } from '@/components/ui';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import './instruments.css';

interface InstrumentPickerProps {
  value?: Instrument;
  onChange: (instrument: Instrument) => void;
  exchange?: string;
  placeholder?: string;
}

export function InstrumentPicker({ value, onChange, exchange, placeholder = 'Search symbol or name…' }: InstrumentPickerProps) {
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const query = useDebouncedValue(text);
  const { data = [], isFetching } = useInstrumentSearch(query, exchange);

  const pick = (instrument: Instrument) => {
    onChange(instrument);
    setText('');
    setOpen(false);
  };

  return (
    <div className="instrument-picker">
      <TextInput
        value={open ? text : value ? `${value.exchange}:${value.symbol}` : text}
        placeholder={placeholder}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && data[0]) pick(data[0]);
          if (e.key === 'Escape') setOpen(false);
        }}
      />
      {open && query && (
        <ul className="instrument-picker__menu">
          {data.length === 0 && <li className="instrument-picker__empty">{isFetching ? 'Searching…' : 'No matches'}</li>}
          {data.map((i) => (
            <li key={i.instrument_id} onMouseDown={() => pick(i)}>
              <span className="instrument-picker__symbol">
                {i.exchange}:{i.symbol}
              </span>
              <span className="instrument-picker__meta">
                {i.instrument_type} · {i.name}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
