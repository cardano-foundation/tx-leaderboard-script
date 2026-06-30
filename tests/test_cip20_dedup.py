import run


def test_dedup_subtracts_same_app_script_overlap():
    compiled = [{"label": "foo", "displayName": "Foo"}]
    app_txs = {"foo": {1, 2, 3}}
    mk = run.app_merge_key("Foo", "foo")
    items = run.cip20_items_from_sets(compiled, app_txs, {mk: {2, 3}})
    assert items == [{"label": "foo", "displayName": "Foo", "txCount": 1}]


def test_dedup_no_overlap_keeps_all():
    compiled = [{"label": "foo", "displayName": "Foo"}]
    app_txs = {"foo": {1, 2, 3}}
    assert run.cip20_items_from_sets(compiled, app_txs, {}) == [
        {"label": "foo", "displayName": "Foo", "txCount": 3}
    ]


def test_dedup_drops_app_fully_covered_by_scripts():
    compiled = [{"label": "foo", "displayName": "Foo"}]
    app_txs = {"foo": {1, 2}}
    mk = run.app_merge_key("Foo", "foo")
    assert run.cip20_items_from_sets(compiled, app_txs, {mk: {1, 2}}) == []


def test_overlap_for_other_app_is_not_subtracted():
    compiled = [{"label": "foo", "displayName": "Foo"}]
    app_txs = {"foo": {1, 2, 3}}
    other = run.app_merge_key("Bar", "bar")
    items = run.cip20_items_from_sets(compiled, app_txs, {other: {1, 2, 3}})
    assert items == [{"label": "foo", "displayName": "Foo", "txCount": 3}]


def test_combined_count_is_distinct_union():
    script_stats = [{"label": "foo", "displayName": "Foo", "txCount": 3}]
    compiled = [{"label": "foo", "displayName": "Foo"}]
    app_txs = {"foo": {1, 2, 3}}
    mk = run.app_merge_key("Foo", "foo")
    cip20_stats = run.cip20_items_from_sets(compiled, app_txs, {mk: {2, 3}})
    result = run.combine_app_stats(script_stats, cip20_stats)
    assert len(result) == 1
    assert result[0]["txCount"] == 4
