import run


def test_merge_sorts_by_txcount_then_label_and_ranks():
    a = [{"label": "b-app", "displayName": "B App", "txCount": 50}]
    b = [{"label": "a-app", "displayName": "A App", "txCount": 50},
         {"label": "big", "displayName": "Big", "txCount": 999}]
    result = run.combine_app_stats(a, b)
    assert [(r["label"], r["rank"]) for r in result] == [
        ("big", 1),     # highest txCount
        ("a-app", 2),   # tie at 50, label "a-app" before "b-app"
        ("b-app", 3),
    ]


def test_collision_sums_txcount():
    a = [{"label": "jpg.store", "displayName": "JPG Store", "txCount": 10}]
    b = [{"label": "jpgstore", "displayName": "jpgstore", "txCount": 5}]
    result = run.combine_app_stats(a, b)
    # canon_name collapses both to merge key "jpgstore"
    assert len(result) == 1
    assert result[0]["txCount"] == 15
    assert result[0]["rank"] == 1


def test_empty_inputs():
    assert run.combine_app_stats([], []) == []


def test_merge_key_falls_back_to_label_when_name_blank():
    assert run.app_merge_key("", "fallback-label") == "fallbacklabel"
    assert run.app_merge_key("Real Name", "x") == "realname"
