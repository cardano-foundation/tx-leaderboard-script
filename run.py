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

# Approx. length of a Cardano epoch, used only for the human-readable label.
EPOCH_LENGTH_DAYS = 5

# Default window used by helpers and external callers (e.g. the CI epoch probe).
REPORTING_WINDOW_EPOCHS = 6

# Reporting windows to generate. Each entry produces its own report file.
#   6 epochs  -> ~30 days  (monthly)
#   73 epochs -> ~365 days (yearly)
REPORTING_WINDOWS = {
    "report.json": 6,
    "report-73epochs.json": 73,
}

BASE_DIR = Path(__file__).parent
SQL_DIR = BASE_DIR / "sql"
CACHE_DIR = BASE_DIR / "data"
CIP20_APPS_FILE = CACHE_DIR / "cip20_apps.json"

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


def load_cip20_allowlist(path=CIP20_APPS_FILE):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return data


def build_prefilter_patterns(allowlist):
    # Coarse SQL prefilter: only rows whose raw metadata json contains one of
    # these substrings are pulled. Precise matching happens in Python against
    # the normalized message.
    patterns = []
    for app in allowlist:
        for m in app.get("match", []):
            if isinstance(m, str) and m.strip():
                patterns.append(f"%{m}%")
    return patterns


def message_texts_from_json(metadata_json):
    # Mirrors the SQL LATERAL: a string msg yields one text, an array msg
    # yields each element as text. Anything else yields nothing.
    if not isinstance(metadata_json, dict):
        return []
    msg = metadata_json.get("msg")
    if isinstance(msg, str):
        return [msg]
    if isinstance(msg, list):
        return [str(x) for x in msg]
    return []


def compile_allowlist(allowlist):
    compiled = []
    for app in allowlist:
        norm_patterns = []
        for m in app.get("match", []):
            if isinstance(m, str) and m.strip():
                n = normalize_msg(m)
                if n:
                    norm_patterns.append(n)
        compiled.append(
            {
                "label": app["label"],
                "displayName": app.get("displayName", app["label"]),
                "matchType": app.get("matchType", "substring"),
                "patterns": norm_patterns,
            }
        )
    return compiled


def cip20_app_tx_sets(rows, allowlist):
    compiled = compile_allowlist(allowlist)
    app_txs = {c["label"]: set() for c in compiled}

    for tx_id, metadata_json in rows:
        for text in message_texts_from_json(metadata_json):
            norm = normalize_msg(text)
            if not norm:
                continue
            for c in compiled:
                matched = False
                for pat in c["patterns"]:
                    if c["matchType"] == "exact":
                        matched = norm == pat
                    else:
                        matched = pat in norm
                    if matched:
                        break
                if matched:
                    app_txs[c["label"]].add(tx_id)

    return compiled, app_txs


def count_cip20_app_txs(rows, allowlist):
    compiled, app_txs = cip20_app_tx_sets(rows, allowlist)

    items = []
    for c in compiled:
        cnt = len(app_txs[c["label"]])
        if cnt > 0:
            items.append(
                {
                    "label": c["label"],
                    "displayName": c["displayName"],
                    "txCount": cnt,
                }
            )
    return items


def cip20_items_from_sets(compiled, app_txs, script_tx_by_app):
    items = []
    for c in compiled:
        merge_key = app_merge_key(c["displayName"], c["label"])
        tx_set = app_txs.get(c["label"], set())
        overlap = script_tx_by_app.get(merge_key)
        if overlap:
            tx_set = tx_set - overlap
        cnt = len(tx_set)
        if cnt > 0:
            items.append(
                {
                    "label": c["label"],
                    "displayName": c["displayName"],
                    "txCount": cnt,
                }
            )
    return items


def get_cip20_app_tx_sets(window_start, window_end):
    allowlist = load_cip20_allowlist()
    if not allowlist:
        return [], {}

    patterns = build_prefilter_patterns(allowlist)
    if not patterns:
        return [], {}

    sql = load_sql("674_messages.sql")
    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,  # type: ignore[arg-type]
                {
                    "start_time": window_start,
                    "end_time": window_end,
                    "patterns": patterns,
                },
            )
            rows = cur.fetchall()

    return cip20_app_tx_sets(rows, allowlist)


def load_sql(filename):
    path = SQL_DIR / filename
    return path.read_text(encoding="utf-8")


def get_epoch_window(window_epochs: int = REPORTING_WINDOW_EPOCHS):
    sql = load_sql("current_epoch.sql")
    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"window_epochs": window_epochs})
            row = cur.fetchone()

    return {
        "chain_current_epoch": row[0],
        "last_completed_epoch": row[1],
        "window_start": row[2],
        "window_end": row[3],
        "window_epochs": window_epochs,
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
                        script_version.get(field)
                        for script in dapp_data.get("scripts", [])
                        for script_version in script.get("versions", [])
                        for field in ("scriptHash", "mintPolicyID")
                        if script_version.get(field)
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


def build_cred_app_map(registries, names):
    cred_to_app: dict[bytes, dict] = {}
    for project_key, cred_hexes in registries.items():
        display_name = names.get(project_key, project_key)
        app = {
            "merge_key": app_merge_key(display_name, project_key),
            "label": canonical_project_name(display_name).replace(" ", "-"),
            "displayName": display_name,
        }
        for h in cred_hexes:
            try:
                b = bytes.fromhex(h)
            except ValueError:
                continue
            cred_to_app.setdefault(b, app)
    return cred_to_app


def get_script_hash_stats(cred_to_app, window_start, window_end):
    if not cred_to_app:
        return []

    creds = list(cred_to_app.keys())
    projects = [cred_to_app[c]["merge_key"] for c in creds]

    sql = load_sql("validator_tx_counts.sql")
    counts: dict[str, int] = {}
    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,  # type: ignore[arg-type]
                {
                    "payment_creds": creds,
                    "projects": projects,
                    "window_start": window_start,
                    "window_end": window_end,
                },
            )
            for project, tx_count in cur.fetchall():
                counts[project] = int(tx_count)

    meta: dict[str, dict] = {}
    for app in cred_to_app.values():
        meta.setdefault(app["merge_key"], app)

    items = []
    for merge_key, cnt in counts.items():
        if cnt <= 0:
            continue
        app = meta[merge_key]
        items.append(
            {
                "label": app["label"],
                "displayName": app["displayName"],
                "txCount": cnt,
            }
        )
    return items


def get_script_tx_by_app(cred_to_app, tx_ids):
    if not cred_to_app or not tx_ids:
        return {}

    creds = list(cred_to_app.keys())
    projects = [cred_to_app[c]["merge_key"] for c in creds]

    sql = load_sql("script_tx_overlap.sql")
    script_tx: dict[str, set] = defaultdict(set)
    with psycopg.connect(**conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,  # type: ignore[arg-type]
                {
                    "payment_creds": creds,
                    "projects": projects,
                    "tx_ids": list(tx_ids),
                },
            )
            for project, tx_id in cur.fetchall():
                script_tx[project].add(tx_id)
    return script_tx


def app_merge_key(display_name, fallback):
    key = canon_name(display_name).replace(" ", "")
    if not key:
        key = canon_name(fallback).replace(" ", "")
    if not key:
        key = fallback
    return key


def combine_app_stats(*item_lists):
    grouped: dict[str, dict[str, str | int]] = {}
    for items in item_lists:
        for entry in items:
            key = app_merge_key(entry["displayName"], entry["label"])
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = {
                    "label": entry["label"],
                    "displayName": entry["displayName"],
                    "txCount": int(entry["txCount"]),
                }
            else:
                existing["txCount"] = int(existing["txCount"]) + int(entry["txCount"])

    items = list(grouped.values())
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


def build_metadata(epoch_info, total_tx_count):
    window_epochs = epoch_info["window_epochs"]
    approx_days = window_epochs * EPOCH_LENGTH_DAYS

    return {
        "generated": datetime.now(timezone.utc).date().isoformat(),
        "chainEpoch": epoch_info["chain_current_epoch"],
        "description": "Transaction stats for reporting period",
        "reportingWindow": {
            "start": epoch_info["window_start"].isoformat(),
            "end": epoch_info["window_end"].isoformat(),
        },
        "epochs": f"~{window_epochs} epochs ({approx_days} days)",
        "totalTxCount": total_tx_count,
    }


def build_report(epoch_info):

    total_tx_count = get_total_tx_count(
        epoch_info["window_start"],
        epoch_info["window_end"],
    )

    window_start = epoch_info["window_start"]
    window_end = epoch_info["window_end"]

    registries, names = fetch_dapps_registries()
    cred_to_app = build_cred_app_map(registries, names)

    script_hash_stats = get_script_hash_stats(
        cred_to_app, window_start, window_end
    )

    compiled, app_txs = get_cip20_app_tx_sets(window_start, window_end)
    message_tx_ids: set = set()
    for tx_set in app_txs.values():
        message_tx_ids |= tx_set
    script_tx_by_app = get_script_tx_by_app(cred_to_app, message_tx_ids)
    cip20_stats = cip20_items_from_sets(compiled, app_txs, script_tx_by_app)

    app_stats = combine_app_stats(script_hash_stats, cip20_stats)

    label_stats = get_metadata_label_stats(
        epoch_info["window_start"],
        epoch_info["window_end"],
    )

    return {
        "metadata": build_metadata(epoch_info, total_tx_count),
        "appStats": app_stats,
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

    # last_completed_epoch is the same regardless of window length, so the
    # skip check can rely on the default window.
    base_window = get_epoch_window()
    last_completed_epoch = base_window["last_completed_epoch"]

    last_pr_epoch = get_last_pr_epoch()
    print(last_pr_epoch, last_completed_epoch)

    if last_pr_epoch == last_completed_epoch:
        print(f"[skip] PR already created for epoch {last_completed_epoch}")
        return

    for filename, window_epochs in REPORTING_WINDOWS.items():
        epoch_info = (
            base_window
            if window_epochs == base_window["window_epochs"]
            else get_epoch_window(window_epochs)
        )
        report = build_report(epoch_info)
        out_path = BASE_DIR / "data" / filename
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[ok] {filename} generated ({window_epochs} epochs) "
            f"for epoch {last_completed_epoch}"
        )

    save_last_pr_epoch(last_completed_epoch)


if __name__ == "__main__":
    main()
