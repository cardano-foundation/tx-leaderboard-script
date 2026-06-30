import run

ALLOWLIST = [
    {"label": "adalink", "displayName": "AdaLink", "match": ["adalink"], "matchType": "substring"},
    {"label": "unfrack.it", "displayName": "Unfrack.it", "match": ["unfrack"], "matchType": "substring"},
    {"label": "cardano.org", "displayName": "Cardano.org", "match": ["cardano.org"], "matchType": "exact"},
]


def counts(rows):
    return {c["label"]: c["txCount"] for c in run.count_cip20_app_txs(rows, ALLOWLIST)}


def test_message_texts_string():
    assert run.message_texts_from_json({"msg": "hello"}) == ["hello"]


def test_message_texts_array():
    assert run.message_texts_from_json({"msg": ["a", "b"]}) == ["a", "b"]


def test_message_texts_array_stringifies_non_strings():
    assert run.message_texts_from_json({"msg": [1, "b"]}) == ["1", "b"]


def test_message_texts_missing_or_wrong_type():
    assert run.message_texts_from_json({"msg": 5}) == []
    assert run.message_texts_from_json({}) == []
    assert run.message_texts_from_json("not a dict") == []


def test_substring_match_on_url():
    assert counts([(1, {"msg": "https://unfrack.it"})]) == {"unfrack.it": 1}


def test_substring_match_on_bracket_tag():
    assert counts([(1, {"msg": "[adalink] You have received a tip!"})]) == {"adalink": 1}


def test_exact_match_positive():
    assert counts([(1, {"msg": "cardano.org"})]) == {"cardano.org": 1}


def test_exact_match_rejects_substring():
    # normalized "powered by cardano org" != "cardano org"
    assert counts([(1, {"msg": "powered by cardano.org"})]) == {}


def test_distinct_tx_deduplicated():
    rows = [(7, {"msg": "adalink one"}), (7, {"msg": "adalink two"})]
    assert counts(rows) == {"adalink": 1}


def test_array_message_matches():
    assert counts([(1, {"msg": ["noise", "[adalink] tip"]})]) == {"adalink": 1}


def test_multiple_apps_counted_independently():
    rows = [(1, {"msg": "adalink"}), (2, {"msg": "https://unfrack.it"})]
    assert counts(rows) == {"adalink": 1, "unfrack.it": 1}


def test_empty_and_non_matching_rows_excluded():
    rows = [(1, {"msg": ""}), (2, {"msg": "totally unrelated"}), (3, {"msg": 123})]
    assert run.count_cip20_app_txs(rows, ALLOWLIST) == []
