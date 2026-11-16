import type { ParamValue } from '@/api/types';
import { Field, TextInput } from '@/components/ui';

interface ParamInputsProps {
  /** The indicator's defaults: decide which inputs exist and whether each is numeric. */
  defaults: Record<string, ParamValue>;
  params: Record<string, ParamValue>;
  onChange: (params: Record<string, ParamValue>) => void;
  /** Show each input under its name (forms) or bare with a placeholder (compact rows). */
  labelled?: boolean;
}

/** One input per indicator param, generated from the backend's defaults. */
export function ParamInputs({ defaults, params, onChange, labelled = true }: ParamInputsProps) {
  return (
    <>
      {Object.keys(defaults).map((key) => {
        const numeric = typeof defaults[key] === 'number';
        const input = (
          <TextInput
            key={key}
            style={{ width: labelled ? 80 : 64 }}
            type={numeric ? 'number' : 'text'}
            value={String(params[key] ?? defaults[key])}
            title={key}
            placeholder={key}
            onChange={(e) => onChange({ ...params, [key]: numeric ? Number(e.target.value) : e.target.value })}
          />
        );
        return labelled ? (
          <Field key={key} label={key}>
            {input}
          </Field>
        ) : (
          input
        );
      })}
    </>
  );
}
