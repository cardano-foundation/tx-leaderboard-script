import json

import run


def test_load_returns_list(tmp_path):
    p = tmp_path / "cip20_apps.json"
    p.write_text(json.dumps([{"label": "x", "match": ["x"]}]), encoding="utf-8")
    assert run.load_cip20_allowlist(p) == [{"label": "x", "match": ["x"]}]


def test_load_missing_file_returns_empty(tmp_path):
    assert run.load_cip20_allowlist(tmp_path / "nope.json") == []


def test_load_non_list_returns_empty(tmp_path):
    p = tmp_path / "cip20_apps.json"
    p.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert run.load_cip20_allowlist(p) == []


def test_build_prefilter_patterns_wraps_each_match():
    allowlist = [
        {"label": "a", "match": ["adalink"]},
        {"label": "c", "match": ["cardano.org"]},
    ]
    assert run.build_prefilter_patterns(allowlist) == ["%adalink%", "%cardano.org%"]


def test_build_prefilter_skips_blank_and_non_str():
    allowlist = [{"label": "a", "match": ["", "  ", 5, "ok"]}]
    assert run.build_prefilter_patterns(allowlist) == ["%ok%"]
