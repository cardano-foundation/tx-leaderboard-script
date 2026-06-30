# Metadata Labels Report

A small utility that compiles a JSON report about Cardano transaction metadata usage over the last ~6 epochs (≈30 days). The `run.py` script connects to a [db-sync](https://github.com/IntersectMBO/cardano-db-sync), looks at the latest fully completed epochs, and combines the on-chain data with several public registries to produce ranked statistics for governance metadata labels and well-known dApps.

## Data sources

- Cardano chain data available through the database (epoch boundaries, transactions, metadata, outputs); all SQL lives in `sql/`.
- [CIP-0010](https://github.com/cardano-foundation/CIPs/blob/master/CIP-0010/registry.json) registry (`cip10_registry.json` cache under `data/`).
- Contract/script registries from [CRFA](https://github.com/mezuny/crfa-offchain-data-registry/tree/main/dApps_v2), [Strica](https://github.com/StricaHQ/cardano-contracts-registry/tree/master/projects), and [Eternl](https://github.com/Tastenkunst/eternl-cardano-registry/tree/main/registry/scripts) for mapping validator script hashes to project names.
- Eternl ingestion uses:
  - [`registry/scripts/script-index.json`](https://github.com/Tastenkunst/eternl-cardano-registry/blob/main/registry/scripts/script-index.json) as the script-hash source (`scripts` object keys grouped by `projectId`).
  - [`registry/projects/*.json`](https://github.com/Tastenkunst/eternl-cardano-registry/tree/main/registry/projects) to resolve project display names (from each file's `label`, with `projectId` fallback).

## Registering a CIP-20 app

Apps whose only on-chain identifier is a CIP-20 (label 674) transaction message can be
attributed on the leaderboard by adding themselves to `data/cip20_apps.json` via a pull
request.

**This is only for apps without Plutus contracts.** If your app deploys validator
scripts or mints under a policy, register your script hashes and mint policy IDs with
the script-hash registries (CRFA, Strica, or Eternl) instead. That path attributes all
of your transactions, not only the ones that carry a message.

Each entry looks like:

```json
{ "label": "unfrack.it", "displayName": "Unfrack.it", "match": ["unfrack"], "matchType": "substring" }
```

- `label`: a stable identifier (lowercase, often your domain). Used as the appStats label.
- `displayName`: the name shown on the leaderboard.
- `match`: one or more patterns to look for in the transaction message. A pattern must
  appear verbatim in the message exactly as your app writes it on chain; matching is
  case-insensitive but otherwise literal, so include any punctuation the message
  contains. For example unfrack.it tags its transactions with `https://unfrack.it`, so
  `unfrack` or `unfrack.it` both work, but `unfrack it` (punctuation rewritten as a
  space) does not match and your app would count zero.
- `matchType`: `substring` matches when the pattern appears anywhere in the message (use
  this when you prefix a stable tag, e.g. messages like `[adalink] ...`, with pattern
  `adalink` or `[adalink]`). `exact` matches when the whole message equals the pattern,
  ignoring case (use this when you emit a single fixed tag).

Pick a pattern distinctive to your app, such as a project tag or your domain. Do not use
a generic word like `cardano` or `swap`; it would falsely match unrelated transactions
and your PR will be rejected. Before submitting, confirm your transactions actually carry
the tag and that it does not collide with another listed app.

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

- `data/report.json`: ~6 epochs (approx. 30 days).
- `data/report-73epochs.json`: ~73 epochs (approx. 365 days).

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
  "metadataLabelStats": [
    {"label": 674, "txCount": 8000, "verified": true, "description": "...", "rank": 1},
    ...
  ]
}
```

The `appStats` section ranks projects by transaction volume from two attribution
sources: registered validator scripts (CRFA/Strica/Eternl script hashes and mint
policies) and the CIP-20 app allowlist (`data/cip20_apps.json`). A project's `txCount`
is the **distinct union** of both sources, deduplicated per project: a transaction that
touches several of a project's own scripts, or that both hits a script and carries a
matching message, is counted once for that project. A transaction touching two
*different* projects still counts once for each. `metadataLabelStats` highlights the
most-used metadata labels and whether they appear in CIP-0010.

## SQL reference

- `sql/current_epoch.sql`: derives the rolling epoch window boundaries.
- `sql/validator_tx_counts.sql`: counts distinct transactions per project (not per credential), grouping output payment credential and mint policy matches by the project each credential belongs to.
- `sql/script_tx_overlap.sql`: for a given set of transaction ids, reports which already hit a project's scripts; used to dedupe CIP-20 message txs against script-attributed txs.
- `sql/label_counts.sql`: counts distinct transactions per metadata label.
- `sql/total_tx_count.sql`: total distinct transactions in the reporting window.
- `sql/674_messages.sql`: candidate label 674 transactions (coarse `json::text` prefilter) for the CIP-20 app allowlist match.
