SELECT
  tm.key AS label,
  COUNT(*) AS metadata_rows,
  COUNT(DISTINCT tm.tx_id) AS distinct_txs
FROM tx_metadata tm
JOIN tx t    ON t.id = tm.tx_id
JOIN block b ON b.id = t.block_id
WHERE b.time >= %(window_start)s
  AND b.time <= %(window_end)s
GROUP BY tm.key
ORDER BY distinct_txs DESC, label ASC;
