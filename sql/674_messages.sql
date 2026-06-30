-- Candidate label-674 transactions for the CIP-20 app allowlist.
-- A coarse json::text prefilter keeps only rows whose raw metadata contains an
-- allowlisted pattern, avoiding a LATERAL msg expansion over every 674 row.
-- The exact msg extraction and matching happen in Python (count_cip20_app_txs).
SELECT
  tm.tx_id,
  tm.json AS metadata_json
FROM tx_metadata tm
JOIN tx t    ON t.id = tm.tx_id
JOIN block b ON b.id = t.block_id
WHERE tm.key = 674
  AND b.time >= %(start_time)s
  AND b.time <  %(end_time)s
  AND tm.json::text ILIKE ANY(%(patterns)s);
