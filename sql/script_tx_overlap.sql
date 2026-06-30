WITH cred_project(payment_cred, project) AS (
  SELECT * FROM unnest(%(payment_creds)s::bytea[], %(projects)s::text[])
),
output_hits AS (
  SELECT
    o.payment_cred AS payment_cred,
    o.tx_id AS tx_id
  FROM tx_out o
  WHERE o.payment_cred = ANY(%(payment_creds)s)
    AND o.tx_id = ANY(%(tx_ids)s)
),
mint_hits AS (
  SELECT
    ma.policy AS payment_cred,
    mtm.tx_id AS tx_id
  FROM ma_tx_mint mtm
  JOIN multi_asset ma ON ma.id = mtm.ident
  WHERE ma.policy = ANY(%(payment_creds)s)
    AND mtm.tx_id = ANY(%(tx_ids)s)
),
all_hits AS (
  SELECT payment_cred, tx_id FROM output_hits
  UNION ALL
  SELECT payment_cred, tx_id FROM mint_hits
)
SELECT DISTINCT
  cp.project,
  h.tx_id
FROM all_hits h
JOIN cred_project cp USING (payment_cred);
