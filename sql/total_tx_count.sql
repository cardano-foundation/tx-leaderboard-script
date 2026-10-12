SELECT COUNT(DISTINCT t.id)::bigint AS tx_count
FROM tx t
JOIN block b ON b.id = t.block_id
WHERE b.time >= %(window_start)s
  AND b.time <= %(window_end)s;
