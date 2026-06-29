SELECT
  COUNT(DISTINCT vp.tx_id) AS vote_tx_count,
  COUNT(*) AS total_votes_cast
FROM voting_procedure vp
JOIN tx t    ON t.id = vp.tx_id
JOIN block b ON b.id = t.block_id
WHERE b.time >= %(window_start)s
  AND b.time <  %(window_end)s;
