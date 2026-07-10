WITH cred_project(payment_cred, project) AS (
  SELECT * FROM unnest(%(payment_creds)s::bytea[], %(projects)s::text[])
),
output_hits AS (
  SELECT
    o.payment_cred AS payment_cred,
    t.id AS tx_id
  FROM tx_out o
  JOIN tx t    ON t.id = o.tx_id
  JOIN block b ON b.id = t.block_id
  WHERE o.payment_cred = ANY(%(payment_creds)s)
    AND b.time >= %(window_start)s
    AND b.time <  %(window_end)s
),
spend_hits AS (
  -- Transactions that spend a UTxO previously locked at the credential
  -- (e.g. escrow withdrawals) but that don't create a new output there,
  -- so they aren't visible to output_hits above.
  SELECT
    o.payment_cred AS payment_cred,
    ti.tx_in_id AS tx_id
  FROM tx_out o
  JOIN tx_in ti ON ti.tx_out_id = o.tx_id AND ti.tx_out_index = o.index
  JOIN tx t    ON t.id = ti.tx_in_id
  JOIN block b ON b.id = t.block_id
  WHERE o.payment_cred = ANY(%(payment_creds)s)
    AND b.time >= %(window_start)s
    AND b.time <  %(window_end)s
),
mint_hits AS (
  SELECT
    ma.policy AS payment_cred,
    t.id AS tx_id
  FROM ma_tx_mint mtm
  JOIN multi_asset ma ON ma.id = mtm.ident
  JOIN tx t           ON t.id = mtm.tx_id
  JOIN block b        ON b.id = t.block_id
  WHERE ma.policy = ANY(%(payment_creds)s)
    AND b.time >= %(window_start)s
    AND b.time <  %(window_end)s
),
all_hits AS (
  SELECT payment_cred, tx_id FROM output_hits
  UNION ALL
  SELECT payment_cred, tx_id FROM spend_hits
  UNION ALL
  SELECT payment_cred, tx_id FROM mint_hits
)
SELECT
  cp.project,
  COUNT(DISTINCT h.tx_id) AS tx_count
FROM all_hits h
JOIN cred_project cp USING (payment_cred)
GROUP BY cp.project;
