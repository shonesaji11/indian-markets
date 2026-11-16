import { PageHeader } from '@/components/ui';
import { CoverageTable } from '@/features/market/CoverageTable';
import { IngestPanel } from '@/features/market/IngestPanel';
import { IngestRunsTable } from '@/features/market/IngestRunsTable';

export function DataPage() {
  return (
    <div className="page">
      <PageHeader title="Data" subtitle="What is stored, what was fetched, and manual downloads. The nightly job keeps this current." />
      <IngestPanel />
      <CoverageTable />
      <IngestRunsTable />
    </div>
  );
}
