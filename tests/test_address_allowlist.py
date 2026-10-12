import pytest

import run

# Real mainnet addresses, expected credentials taken from tx_out.payment_cred in db-sync.
ENTERPRISE_KEY = "addr1vy740r73x2w3du2xxt76cs4hdml4zw2c5h7tddcyf3jauys9tyns4"
ENTERPRISE_KEY_CRED = "3d578fd1329d16f14632fdac42b76eff513958a5fcb6b7044c65de12"
BASE_KEY = (
    "addr1q8wftxz8n7qwwkjy9dkasnxywztpguq32dvg0hwcarj9wrrs7f0ldlv6muesavcc43yx3x"
    "a2wgw49hk4eldzcdj5pcrqa3arf5"
)
BASE_KEY_CRED = "dc9598479f80e75a442b6dd84cc47096147011535887ddd8e8e4570c"
ENTERPRISE_SCRIPT = "addr1w99se2k9d0vmdrz78qr2keekylgkk45dz3m8g0x2tlfl88chm4czv"
ENTERPRISE_SCRIPT_CRED = "4b0caac56bd9b68c5e3806ab673627d16b568d1476743cca5fd3f39f"
BASE_SCRIPT = (
    "addr1z8srqftqemf0mjlukfszd97ljuxdp44r372txfcr75wrz2auzrlrz2kdd83wzt9u9n9qt2"
    "swgvhrmmn96k55nq6yuj4qw992w9"
)
BASE_SCRIPT_CRED = "e0302560ced2fdcbfcb2602697df970cd0d6a38f94b32703f51c312b"

REWARD = "stake1u9c0yhlklkdd7vcwkvv2cjrgnw48y82jmm2ulk3vxe2qupsv2va8g"
# ENTERPRISE_KEY re-encoded for testnet, and with a testnet header under the mainnet prefix.
TESTNET = "addr_test1vq740r73x2w3du2xxt76cs4hdml4zw2c5h7tddcyf3jauys7rs0ls"
TESTNET_HEADER = "addr1vq740r73x2w3du2xxt76cs4hdml4zw2c5h7tddcyf3jauys9e5zsj"
# Checksum valid but malformed: BASE_KEY cut after the payment part, ENTERPRISE_KEY
# with a nonzero padding bit or an extra 5 bit group, and an empty payload.
TRUNCATED_BASE = "addr1q8wftxz8n7qwwkjy9dkasnxywztpguq32dvg0hwcarj9wrqamdc6j"
BAD_PADDING = "addr1vy740r73x2w3du2xxt76cs4hdml4zw2c5h7tddcyf3jauy3casxd8"
EXTRA_GROUP = "addr1vy740r73x2w3du2xxt76cs4hdml4zw2c5h7tddcyf3jauysqec9rxf"
EMPTY = "addr1mykd6t"
# ENTERPRISE_KEY as a well formed pointer address, rejected because pointers are not supported.
POINTER = "addr1gy740r73x2w3du2xxt76cs4hdml4zw2c5h7tddcyf3jauyspqgpsp29729"


@pytest.mark.parametrize(
    "address, cred",
    [
        (ENTERPRISE_KEY, ENTERPRISE_KEY_CRED),
        (BASE_KEY, BASE_KEY_CRED),
        (ENTERPRISE_SCRIPT, ENTERPRISE_SCRIPT_CRED),
        (BASE_SCRIPT, BASE_SCRIPT_CRED),
        (ENTERPRISE_KEY.upper(), ENTERPRISE_KEY_CRED),
    ],
)
def test_payment_cred_matches_db_sync(address, cred):
    assert run.address_payment_cred(address).hex() == cred


@pytest.mark.parametrize(
    "address",
    [
        REWARD,
        TESTNET,
        TESTNET_HEADER,
        TRUNCATED_BASE,
        BAD_PADDING,
        EXTRA_GROUP,
        EMPTY,
        POINTER,
        ENTERPRISE_KEY[:-1] + "5",
        "not an address",
    ],
)
def test_payment_cred_rejects(address):
    with pytest.raises(ValueError):
        run.address_payment_cred(address)


def test_cred_map_entry_shape():
    allowlist = [
        {"label": "x-app", "displayName": "X App", "addresses": [ENTERPRISE_KEY, BASE_KEY]}
    ]
    cred_map = run.address_cred_map(allowlist)
    app = {"merge_key": "xapp", "label": "x-app", "displayName": "X App"}
    assert cred_map == {
        bytes.fromhex(ENTERPRISE_KEY_CRED): app,
        bytes.fromhex(BASE_KEY_CRED): app,
    }


def test_cred_map_rejects_duplicate_credential():
    allowlist = [
        {"label": "a", "addresses": [ENTERPRISE_KEY]},
        {"label": "b", "addresses": [ENTERPRISE_KEY]},
    ]
    with pytest.raises(ValueError, match="duplicate payment credential"):
        run.address_cred_map(allowlist)


def test_cred_map_rejects_duplicate_label():
    allowlist = [
        {"label": "a", "addresses": [ENTERPRISE_KEY]},
        {"label": "a", "addresses": [BASE_KEY]},
    ]
    with pytest.raises(ValueError, match="duplicate label"):
        run.address_cred_map(allowlist)


@pytest.mark.parametrize("entry", [{"label": "a"}, {"label": "a", "addresses": []}])
def test_cred_map_rejects_entry_without_addresses(entry):
    with pytest.raises(ValueError, match="no addresses"):
        run.address_cred_map([entry])


def test_load_missing_file_returns_empty(tmp_path):
    assert run.load_address_allowlist(tmp_path / "nope.json") == []


def test_load_non_list_raises(tmp_path):
    p = tmp_path / "address_apps.json"
    p.write_text('{"label": "a", "addresses": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a list"):
        run.load_address_allowlist(p)


def test_shipped_allowlist_is_valid():
    run.address_cred_map(run.load_address_allowlist())

