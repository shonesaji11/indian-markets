import { useEffect, useState } from 'react';
import { useIndicators } from '@/api/queries';
import type { ParamValue } from '@/api/types';
import { Button, Field, Select } from '@/components/ui';
import { ParamInputs } from './ParamInputs';

export interface IndicatorSelection {
  name: string;
  params: Record<string, ParamValue>;
}

/** Choose an indicator and edit its params. The form is generated from the backend's defaults. */
export function IndicatorPicker({ onAdd }: { onAdd: (selection: IndicatorSelection) => void }) {
  const { data: indicators = [] } = useIndicators();
  const [name, setName] = useState('');
  const [params, setParams] = useState<Record<string, ParamValue>>({});
  const spec = indicators.find((i) => i.name === name);

  useEffect(() => {
    if (!name && indicators[0]) setName(indicators[0].name);
  }, [indicators, name]);

  useEffect(() => {
    setParams(spec ? { ...spec.params } : {});
  }, [spec]);

  if (!spec) return null;

  return (
    <div className="ui-row">
      <Field label="Indicator">
        <Select
          value={name}
          options={indicators.map((i) => ({ value: i.name, label: `${i.name} v${i.version}` }))}
          onChange={setName}
          title={spec.description}
        />
      </Field>
      <ParamInputs defaults={spec.params} params={params} onChange={setParams} />
      <Button variant="primary" onClick={() => onAdd({ name, params })}>
        Add
      </Button>
    </div>
  );
}
