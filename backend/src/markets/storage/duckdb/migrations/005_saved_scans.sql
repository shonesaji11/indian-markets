-- Custom scans saved from the Scans page. `definition` is JSON:
-- {"filter": <filter tree, see engine/screener.py>, "universe": "nifty500", "include_indices": false}
CREATE TABLE saved_scans (
    scan_id    VARCHAR PRIMARY KEY,
    name       VARCHAR   NOT NULL UNIQUE,
    definition VARCHAR   NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

-- The Daily stats page's old "At 52-week high" checkbox, as a starter scan.
INSERT INTO saved_scans (scan_id, name, definition) VALUES (
    'at-52w-high',
    'At 52-week high',
    '{"filter": {"type": "group", "match": "all", "items": [{"type": "condition", "left": {"type": "field", "field": "high"}, "op": "gte", "right": {"type": "field", "field": "high_52w"}}]}, "universe": "nifty500", "include_indices": false}'
);
