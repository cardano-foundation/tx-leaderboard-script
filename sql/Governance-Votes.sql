SELECT b.epoch_no,
       Count(DISTINCT vp.tx_id) AS vote_tx_count,
       Count(*)                 AS total_votes_cast
FROM   voting_procedure vp
       JOIN tx
         ON tx.id = vp.tx_id
       JOIN block b
         ON b.id = tx.block_id
GROUP  BY b.epoch_no
ORDER  BY b.epoch_no DESC; 
