import { useEffect, useState } from 'react';
import { useDeleteScan, useSaveScan, useSavedScans } from '@/api/queries';
import type { SavedScan, ScanDefinition } from '@/api/types';
import { Button, ErrorMessage, Field, Select, TextInput } from '@/components/ui';

interface SavedScansProps {
  /** Id of the loaded saved scan, '' when none. */
  current: string;
  /** What "Save" stores: the filter, universe and index toggle on screen. */
  definition: ScanDefinition;
  onLoad: (scan: SavedScan | undefined) => void;
}

/** Load, save (create or overwrite by name) and delete saved scans. */
export function SavedScans({ current, definition, onLoad }: SavedScansProps) {
  const { data: scans = [] } = useSavedScans();
  const save = useSaveScan();
  const remove = useDeleteScan();
  const loaded = scans.find((s) => s.scan_id === current);
  const [name, setName] = useState('');

  useEffect(() => setName(loaded?.name ?? ''), [loaded?.name]);

  const onSave = () =>
    save.mutate(
      { name, definition },
      { onSuccess: ({ scan_id }) => onLoad({ scan_id, name, definition, created_at: '', updated_at: '' }) },
    );

  return (
    <>
      <Field label="Saved scans">
        <Select
          value={loaded ? current : ''}
          options={[{ value: '', label: 'New scan' }, ...scans.map((s) => ({ value: s.scan_id, label: s.name }))]}
          onChange={(id) => onLoad(scans.find((s) => s.scan_id === id))}
        />
      </Field>
      <Field label="Name">
        <TextInput value={name} placeholder="Breakouts on volume" onChange={(e) => setName(e.target.value)} style={{ width: 180 }} />
      </Field>
      <Button onClick={onSave} loading={save.isPending} disabled={!name.trim()}>
        {loaded && loaded.name === name.trim() ? 'Update' : 'Save'}
      </Button>
      {loaded && (
        <Button variant="ghost" loading={remove.isPending} onClick={() => remove.mutate(loaded.scan_id, { onSuccess: () => onLoad(undefined) })}>
          Delete
        </Button>
      )}
      <ErrorMessage error={save.error ?? remove.error} />
    </>
  );
}
