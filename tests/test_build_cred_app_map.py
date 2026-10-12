import run

HASH_A = "aa" * 28
HASH_B = "bb" * 28


def test_strica_names_alias_to_crfa_and_eternl_keys():
    assert run.canonical_project_name("Splash Protocol") == "splash"
    assert run.canonical_project_name("Intersect Budget Contracts") == "intersect"


def test_aliased_display_name_keeps_short_label():
    # Strica's display name wins, the label still matches the CRFA/Eternl key.
    cred_map = run.build_cred_app_map({"splash": [HASH_A]}, {"splash": "Splash Protocol"})
    assert cred_map[bytes.fromhex(HASH_A)]["label"] == "splash"


def test_shared_hash_counts_for_first_project_and_warns(capsys):
    registries = {"foo": [HASH_A, HASH_B], "bar": [HASH_A]}
    names = {"foo": "Foo", "bar": "Bar"}
    cred_map = run.build_cred_app_map(registries, names)
    assert cred_map[bytes.fromhex(HASH_A)]["merge_key"] == "foo"
    out = capsys.readouterr().out
    assert "1 script hashes listed for both Foo and Bar, counted for Foo only" in out


def test_warning_counts_case_variants_once(capsys):
    registries = {"foo": [HASH_A], "bar": [HASH_A, HASH_A.upper()]}
    run.build_cred_app_map(registries, {"foo": "Foo", "bar": "Bar"})
    assert "1 script hashes listed for both Foo and Bar" in capsys.readouterr().out


def test_no_warning_without_shared_hashes(capsys):
    run.build_cred_app_map({"foo": [HASH_A], "bar": [HASH_B]}, {"foo": "Foo", "bar": "Bar"})
    assert "[warn]" not in capsys.readouterr().out
