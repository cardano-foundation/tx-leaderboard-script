import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import psycopg
import requests
from dotenv import load_dotenv

load_dotenv()

REPORTING_WINDOW_EPOCHS = 6

BASE_DIR = Path(__file__).parent
SQL_DIR = BASE_DIR / "sql"
CACHE_DIR = BASE_DIR / "data"

LAST_EPOCH_FILE = BASE_DIR / "data" / "last_pr_epoch.txt"

CIP10_REGISTRY_URL = (
    "https://raw.githubusercontent.com/cardano-foundation/CIPs/master/"
    "CIP-0010/registry.json"
)
CRFA_REGISTRY_URL = (
    "https://api.github.com/repos/mezuny/crfa-offchain-data-registry/contents/"
    "dApps?ref=main"
)
STRICA_REGISTRY_URL = (
    "https://api.github.com/repos/StricaHQ/cardano-contracts-registry/contents/"
    "projects?ref=master"
)
ETERNL_SCRIPT_INDEX_URL = (
    "https://raw.githubusercontent.com/Tastenkunst/eternl-cardano-registry/main/"
    "registry/scripts/script-index.json"
)
ETERNL_PROJECTS_REGISTRY_URL = (
    "https://api.github.com/repos/Tastenkunst/eternl-cardano-registry/contents/"
    "registry/projects?ref=main"
)

ALIASES = {"jpgstore": "jpg.store"}
MIN_TX_THRESHOLD = 100
MAX_GROUPS = 200

conninfo = {
    "host": os.environ["DB_HOST"],
    "port": int(os.environ["DB_PORT"]),
    "dbname": os.environ["DB_NAME"],
    "user": os.environ["DB_USER"],
}

if "DB_PASSWORD" in os.environ:
    conninfo["password"] = os.environ["DB_PASSWORD"]


def check_db():
    with psycopg.connect(**conninfo, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")


def get_last_pr_epoch():
    if LAST_EPOCH_FILE.exists():
        return int(LAST_EPOCH_FILE.read_text().strip())
    return None


def save_last_pr_epoch(epoch: int):
    LAST_EPOCH_FILE.write_text(str(epoch), encoding="utf-8")


def canonical_project_name(name):
    key = name.strip().lower()
    return ALIASES.get(key, key)


def canon_name(name):
    name = name.strip()
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    name = name.lower()
    name = re.sub(r"[^a-z0-9]+", " ", name)
    name = " ".join(name.split())
    return name


def normalize_msg(msg: str) -> str:
    non_alnum = re.compile(r"[^a-z0-9]+")
    msg = unicodedata.normalize("NFKD", msg)
    msg = "".join(ch for ch in msg if not unicodedata.combining(ch))
    msg = msg.lower()
    msg = non_alnum.sub(" ", msg)
    msg = " ".join(msg.split())
    return msg.strip()


def load_sql(filename):
    path = SQL_DIR / filename
    return path.read_text(encoding="utf-8")


def get_epoch_window():
    sql = load_sql("current_epoch.sql")
    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"window_epochs": REPORTING_WINDOW_EPOCHS})
            row = cur.fetchone()

    return {
        "chain_current_epoch": row[0],
        "last_completed_epoch": row[1],
        "window_start": row[2],
        "window_end": row[3],
    }


def fetch_cip10_registry(cache_path):
    try:
        r = requests.get(CIP10_REGISTRY_URL, timeout=30)
        r.raise_for_status()
        data = r.json()
        cache_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return data
    except Exception as e:
        if cache_path.exists():
            print(
                f"[warn] Failed to fetch registry ({e}); using cache: {cache_path}"
            )
            return json.loads(cache_path.read_text(encoding="utf-8"))
        raise


def fetch_dapps_registries():
    try:
        crfa_registry, crfa_registry_names = extract_registry(
            CRFA_REGISTRY_URL, "CRFA"
        )
        strica_registry, strica_registry_names = extract_registry(
            STRICA_REGISTRY_URL, "STRICA"
        )
        eternl_registry, eternl_registry_names = extract_eternl_registry()

        registries = merge_dicts_of_lists(
            crfa_registry, strica_registry, eternl_registry
        )
        names = merge_dicts_of_project_names(
            {
                "CRFA": crfa_registry_names,
                "STRICA": strica_registry_names,
                "ETERNL": eternl_registry_names,
            },
            preferred_registry="STRICA",
        )

        return registries, names
    except Exception as e:
        print("ERROR fetch_dapps_registries(): ", e)
        raise


def merge_dicts_of_project_names(
    registries: dict[str, dict[str, str]],
    preferred_registry: Literal["CRFA", "STRICA", "ETERNL"],
):
    merged = {}

    for registry_id, names in registries.items():
        for canon_name, display_name in names.items():
            if canon_name not in merged:
                merged[canon_name] = display_name

    preferred = registries.get(preferred_registry, {})
    for canon_name, display_name in preferred.items():
        merged[canon_name] = display_name

    return merged


def merge_dicts_of_lists(*dicts):
    merged = defaultdict(set)

    for d in dicts:
        for key, values in d.items():
            merged[key].update(values)

    return {k: sorted(v) for k, v in merged.items()}


def extract_registry(registry_url, registry_id: Literal["CRFA", "STRICA"]):
    try:
        registry = defaultdict(set)
        registry_names = defaultdict()

        r = requests.get(registry_url, timeout=30)
        r.raise_for_status()
        data = r.json()

        for dapp in data:
            dapp_json_url = dapp["download_url"]

            if not dapp_json_url:
                continue

            dapp_r = requests.get(dapp_json_url, timeout=30)
            dapp_r.raise_for_status()
            dapp_data = dapp_r.json()

            project_name = dapp_data["projectName"]
            normalized_project_name = canonical_project_name(project_name)
            scriptHashes = set()

            match registry_id:
                case "CRFA":
                    scriptHashes = {
                        script_version.get("scriptHash")
                        for script in dapp_data.get("scripts", [])
                        for script_version in script.get("versions", [])
                        if script_version.get("scriptHash")
                    }
                case "STRICA":
                    scriptHashes = {
                        script.get("scriptHash")
                        for script in dapp_data.get("contracts", [])
                        if script.get("scriptHash")
                    }

            registry[normalized_project_name].update(scriptHashes)
            registry_names[normalized_project_name] = project_name

        return registry, registry_names
    except Exception as e:
        print("ERROR:", e)
        raise


def extract_eternl_registry():
    try:
        registry = defaultdict(set)
        registry_names = defaultdict()

        scripts_r = requests.get(ETERNL_SCRIPT_INDEX_URL, timeout=30)
        scripts_r.raise_for_status()
        scripts_data = scripts_r.json()

        scripts = scripts_data.get("scripts", {})
        if not isinstance(scripts, dict):
            return {}, {}

        for script_hash, info in scripts.items():
            if not isinstance(script_hash, str) or not isinstance(info, dict):
                continue

            project_id = info.get("projectId")
            if not isinstance(project_id, str) or not project_id.strip():
                continue

            normalized_project_name = canonical_project_name(project_id)
            registry[normalized_project_name].add(script_hash)
            registry_names[normalized_project_name] = project_id

        projects_r = requests.get(ETERNL_PROJECTS_REGISTRY_URL, timeout=30)
        projects_r.raise_for_status()
        projects_index = projects_r.json()

        if isinstance(projects_index, list):
            for project_entry in projects_index:
                if not isinstance(project_entry, dict):
                    continue

                file_name = project_entry.get("name")
                download_url = project_entry.get("download_url")

                if (
                    not isinstance(file_name, str)
                    or not file_name.endswith(".json")
                    or not isinstance(download_url, str)
                ):
                    continue

                project_id = file_name[: -len(".json")]
                normalized_project_name = canonical_project_name(project_id)
                if normalized_project_name not in registry:
                    continue

                project_r = requests.get(download_url, timeout=30)
                project_r.raise_for_status()
                project_data = project_r.json()

                project_label = project_data.get("label")
                if isinstance(project_label, str) and project_label.strip():
                    registry_names[normalized_project_name] = project_label

        return (
            {k: sorted(v) for k, v in registry.items()},
            dict(registry_names),
        )
    except Exception as e:
        print("ERROR extract_eternl_registry():", e)
        raise


def get_registries_stats(window_start, window_end):
    sql = load_sql("validator_tx_counts.sql")
    registries, names = fetch_dapps_registries()

    cred_to_project: dict[bytes, str] = {}
    for project_key, cred_hexes in registries.items():
        for h in cred_hexes:
            try:
                b = bytes.fromhex(h)
            except ValueError:
                continue
            cred_to_project.setdefault(b, project_key)

    all_creds = list(cred_to_project.keys())

    counts_by_project = Counter()

    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,  # type: ignore[arg-type]
                {
                    "payment_creds": all_creds,
                    "window_start": window_start,
                    "window_end": window_end,
                },
            )

            for payment_cred, tx_count in cur.fetchall():
                project_key = cred_to_project.get(payment_cred)
                if project_key:
                    counts_by_project[project_key] += int(tx_count)

    items = []
    for project_key, cnt in counts_by_project.items():
        if cnt <= 0:
            continue

        items.append(
            {
                "label": project_key.replace(" ", "-"),
                "displayName": names.get(project_key, project_key),
                "txCount": int(cnt),
            }
        )

    items.sort(key=lambda x: (-x["txCount"], x["label"]))
    for i, item in enumerate(items, start=1):
        item["rank"] = i

    return items


def extract_labels_and_descriptions(registry):
    labels = []
    desc = {}
    for item in registry:
        label = item.get("transaction_metadatum_label")
        if isinstance(label, int):
            labels.append(label)
            d = item.get("description")
            if isinstance(d, str):
                desc[label] = d
    labels = sorted(set(labels))
    return labels, desc


def get_metadata_label_stats(window_start, window_end):
    cache_path = CACHE_DIR / "cip10_registry.json"
    registry = fetch_cip10_registry(cache_path)

    cip_labels, cip_desc = extract_labels_and_descriptions(registry)
    cip_set = set(cip_labels)

    sql = load_sql("label_counts.sql")

    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,  # type: ignore[arg-type]
                {
                    "window_start": window_start,
                    "window_end": window_end,
                },
            )
            rows = cur.fetchall()

    items = []
    for label, _, distinct_txs in rows:
        items.append(
            {
                "label": int(label),
                "txCount": int(distinct_txs),
                "verified": label in cip_set,
                "description": cip_desc.get(label),
            }
        )

    items.sort(key=lambda x: (-x["txCount"], x["label"]))
    for i, item in enumerate(items, start=1):
        item["rank"] = i

    return items


# def get_674_message_frequency_stats():
#     sql = load_sql("674_messages.sql")
#     counts = Counter()
#     tx_seen = defaultdict(set)
#     total_tx_with_msg = set()
#
#     with psycopg.connect(**conninfo) as conn:
#         with conn.cursor() as cur:
#             cur.execute(sql, {"window_days": REPORTING_WINDOW_DAYS})  # type: ignore[arg-type]
#             for tx_id, raw_msg in cur.fetchall():
#                 if raw_msg is None:
#                     continue
#                 total_tx_with_msg.add(tx_id)
#
#                 norm = normalize_msg(str(raw_msg))
#                 if not norm:
#                     continue
#
#                 key = norm
#
#                 if key in tx_seen[tx_id]:
#                     continue
#                 tx_seen[tx_id].add(key)
#
#                 counts[key] += 1
#
#     frequent = [
#         (k, v) for k, v in counts.most_common() if v >= MIN_TX_THRESHOLD
#     ]
#     frequent = frequent[:MAX_GROUPS]
#
#     frequent_set = {k for k, _ in frequent}
#     other_tx_count = sum(v for k, v in counts.items() if k not in frequent_set)
#
#     return {
#         "totalTxWithMsg": len(total_tx_with_msg),
#         "groups": [{"message": k, "txCount": v} for k, v in frequent],
#         "otherTxCount": other_tx_count,
#     }


def get_total_tx_count(window_start, window_end):
    sql = load_sql("total_tx_count.sql")
    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,  # type: ignore[arg-type]
                {
                    "window_start": window_start,
                    "window_end": window_end,
                },
            )

            (cnt,) = cur.fetchone()  # type: ignore[arg-type]
            return int(cnt)


def get_vote_stats(window_start, window_end, total_tx_count: int):
    sql = load_sql("vote_stats.sql")
    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,  # type: ignore[arg-type]
                {
                    "window_start": window_start,
                    "window_end": window_end,
                },
            )

            vote_tx_count, total_votes_cast = cur.fetchone()  # type: ignore[arg-type]

    vote_tx_count = int(vote_tx_count or 0)
    total_votes_cast = int(total_votes_cast or 0)
    vote_tx_share_pct = 0.0
    if total_tx_count > 0:
        vote_tx_share_pct = round((vote_tx_count / total_tx_count) * 100, 4)

    return {
        "voteTxCount": vote_tx_count,
        "totalVotesCast": total_votes_cast,
        "voteTxSharePct": vote_tx_share_pct,
    }


def build_metadata(epoch_info, total_tx_count):

    return {
        "generated": datetime.now(timezone.utc).date().isoformat(),
        "chainEpoch": epoch_info["chain_current_epoch"],
        "description": "Transaction stats for reporting period",
        "reportingWindow": {
            "start": epoch_info["window_start"].isoformat(),
            "end": epoch_info["window_end"].isoformat(),
        },
        "epochs": "~6 epochs (30 days)",
        "totalTxCount": total_tx_count,
    }


def build_report(epoch_info):

    total_tx_count = get_total_tx_count(
        epoch_info["window_start"],
        epoch_info["window_end"],
    )

    app_stats = get_registries_stats(
        epoch_info["window_start"],
        epoch_info["window_end"],
    )

    vote_stats = get_vote_stats(
        epoch_info["window_start"],
        epoch_info["window_end"],
        total_tx_count,
    )

    label_stats = get_metadata_label_stats(
        epoch_info["window_start"],
        epoch_info["window_end"],
    )

    return {
        "metadata": build_metadata(epoch_info, total_tx_count),
        "appStats": app_stats,
        "voteStats": vote_stats,
        "metadataLabelStats": label_stats,
        # "messageStats": {
        #     "label": 674,
        #     "threshold": MIN_TX_THRESHOLD,
        #     **get_674_message_frequency_stats(),
        # },
    }


def main():
    check_db()
    os.makedirs("data", exist_ok=True)

    epoch_info = get_epoch_window()
    last_completed_epoch = epoch_info["last_completed_epoch"]

    last_pr_epoch = get_last_pr_epoch()
    print(last_pr_epoch, last_completed_epoch)

    if last_pr_epoch == last_completed_epoch:
        print(f"[skip] PR already created for epoch {last_completed_epoch}")
        return

    report = build_report(epoch_info)
    out_path = BASE_DIR / "data" / "report.json"
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    save_last_pr_epoch(last_completed_epoch)
    print(f"[ok] Report generated for epoch {last_completed_epoch}")


if __name__ == "__main__":
    main()
