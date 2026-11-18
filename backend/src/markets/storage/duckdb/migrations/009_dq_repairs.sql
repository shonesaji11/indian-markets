-- Repair attempts on data-quality issues (pipelines/repair.py): the nightly repair step
-- re-downloads the dates of fixable issues, at most once a week each and a few times in all.
ALTER TABLE dq_issues ADD COLUMN repair_attempts INTEGER DEFAULT 0;
ALTER TABLE dq_issues ADD COLUMN last_repair_at TIMESTAMP;
