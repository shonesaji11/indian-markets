import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react';

interface FieldProps {
  label: ReactNode;
  children: ReactNode;
}

/** Label + control, stacked. Wrap any input in it for consistent spacing. */
export function Field({ label, children }: FieldProps) {
  return (
    <label className="ui-field">
      <span className="ui-field__label">{label}</span>
      {children}
    </label>
  );
}

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={['ui-input', className].filter(Boolean).join(' ')} {...rest} />;
}

export interface SelectOption<T extends string> {
  value: T;
  label?: ReactNode;
}

interface SelectProps<T extends string> extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'onChange' | 'value'> {
  value: T;
  options: readonly (T | SelectOption<T>)[];
  onChange: (value: T) => void;
}

interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
}

export function Checkbox({ checked, onChange, children }: CheckboxProps) {
  return (
    <label className="ui-checkbox">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {children}
    </label>
  );
}

interface SegmentedControlProps<T extends string> {
  value: T;
  options: readonly SelectOption<T>[];
  onChange: (value: T) => void;
  'aria-label'?: string;
}

/** A small set of mutually exclusive options shown side by side. */
export function SegmentedControl<T extends string>({ value, options, onChange, ...rest }: SegmentedControlProps<T>) {
  return (
    <div className="ui-segmented" role="group" aria-label={rest['aria-label']}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label ?? o.value}
        </button>
      ))}
    </div>
  );
}

export function Select<T extends string>({ value, options, onChange, className, ...rest }: SelectProps<T>) {
  return (
    <select
      className={['ui-select', className].filter(Boolean).join(' ')}
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      {...rest}
    >
      {options.map((o) => {
        const opt = typeof o === 'string' ? { value: o } : o;
        return (
          <option key={opt.value} value={opt.value}>
            {opt.label ?? opt.value}
          </option>
        );
      })}
    </select>
  );
}
