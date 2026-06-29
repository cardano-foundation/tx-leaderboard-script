# Metadata Labels Report

A small utility that compiles a JSON report about Cardano transaction metadata usage over the last ~6 epochs (≈30 days). The `run.py` script connects to a [db-sync](https://github.com/IntersectMBO/cardano-db-sync), looks at the latest fully completed epochs, and combines the on-chain data with several public registries to produce ranked statistics for governance metadata labels and well-known dApps.

## Data sources

- Cardano chain data available through the database (epoch boundaries, transactions, metadata, outputs); all SQL lives in `sql/`.
- [CIP-0010](https://github.com/cardano-foundation/CIPs/blob/master/CIP-0010/registry.json) registry (`cip10_registry.json` cache under `data/`).
- Contract/script registries from [CRFA](https://github.com/mezuny/crfa-offchain-data-registry/tree/main/dApps_v2), [Strica](https://github.com/StricaHQ/cardano-contracts-registry/tree/master/projects), and [Eternl](https://github.com/Tastenkunst/eternl-cardano-registry/tree/main/registry/scripts) for mapping validator script hashes to project names.
- Eternl ingestion uses:
  - [`registry/scripts/script-index.json`](https://github.com/Tastenkunst/eternl-cardano-registry/blob/main/registry/scripts/script-index.json) as the script-hash source (`scripts` object keys grouped by `projectId`).
  - [`registry/projects/*.json`](https://github.com/Tastenkunst/eternl-cardano-registry/tree/main/registry/projects) to resolve project display names (from each file's `label`, with `projectId` fallback).

## Configuration

Set the database credentials via environment variables or a `.env` file (loaded automatically):

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cexplorer
DB_USER=user
DB_PASSWORD=secret
```

`run.py` also honors `data/last_pr_epoch.txt`, which stores the last epoch that produced a report so the script can skip duplicate runs.

## Usage

1. Ensure the database is caught up and the credentials above work.
2. (Optional) Remove `data/last_pr_epoch.txt` if you need to re-emit a report for the same epoch.
3. Run the generator:

```
python run.py
```

## Output

Each run emits two reports with the same structure but different reporting windows:

- `data/report.json` – ~6 epochs (≈30 days).
- `data/report-73epochs.json` – ~73 epochs (≈365 days).

`data/report.json` contains:

```
{
  "metadata": {
    "generated": "YYYY-MM-DD",
    "chainEpoch": 512,
    "description": "Transaction stats for reporting period",
    "reportingWindow": {
      "start": "...",
      "end": "..."
    },
    "epochs": "~6 epochs (30 days)",
    "totalTxCount": 123456
  },
  "appStats": [
    {"label": "jpg.store", "displayName": "JPG Store", "txCount": 4200, "rank": 1},
    ...
  ],
  "voteStats": {
    "voteTxCount": 123,
    "totalVotesCast": 456,
    "voteTxSharePct": 0.0996
  },
  "metadataLabelStats": [
    {"label": 674, "txCount": 8000, "verified": true, "description": "...", "rank": 1},
    ...
  ]
}
```

The `appStats` section ranks projects by the number of transactions seen on their registered validator scripts, `voteStats` summarizes governance voting activity in the same reporting window (including the share of all transactions), and `metadataLabelStats` highlights the most-used metadata labels and whether they appear in CIP-0010. (A more detailed label 674 message breakdown exists in `sql/674_messages.sql` and is easy to re-enable if needed.)

`voteStats` fields:
- `voteTxCount`: distinct transactions that include at least one voting procedure.
- `totalVotesCast`: total number of voting procedures recorded (a single transaction may include multiple votes).
- `voteTxSharePct`: percentage of all transactions in the reporting window that are vote transactions (`voteTxCount / totalTxCount * 100`).

## SQL reference

- `sql/current_epoch.sql` – derives the rolling epoch window boundaries.
- `sql/validator_tx_counts.sql` – counts distinct transactions per known script hash by combining output payment credential matches and mint policy matches.
- `sql/label_counts.sql` – counts distinct transactions per metadata label.
- `sql/total_tx_count.sql` – total distinct transactions in the reporting window.
- `sql/vote_stats.sql` – counts distinct vote transactions and total votes cast in the reporting window.
- `sql/674_messages.sql` – helper query to inspect individual label 674 `msg` entries (currently unused).
