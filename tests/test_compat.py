from zeus_dev_helper_mcp.compat import (
    CLIENT_FLOOR,
    compat_check,
    eval_feature_gates,
    parse_version,
)
from zeus_dev_helper_mcp.config import HelperConfig


def test_parse_version() -> None:
    assert parse_version("0.7.29") == (0, 7, 29)
    assert parse_version("v0.8.0") == (0, 8, 0)
    assert parse_version("0.7") == (0, 7, 0)
    assert parse_version("") is None


def test_feature_gates_0_7_6() -> None:
    gates = {g["id"]: g for g in eval_feature_gates("0.7.6")}
    assert gates["semantic_cache"]["status"] == "pass"
    assert gates["invalid_req_id"]["status"] == "pass"
    assert gates["v1_removed"]["status"] == "pass"


def test_feature_gates_old_engine() -> None:
    gates = {g["id"]: g for g in eval_feature_gates("0.6.9")}
    assert gates["semantic_cache"]["status"] == "fail"
    assert "lacks" in gates["semantic_cache"]["detail"]
    assert gates["invalid_req_id"]["status"] == "fail"


def test_feature_gates_0_7_5_lacks_cache() -> None:
    gates = {g["id"]: g for g in eval_feature_gates("0.7.5")}
    assert gates["semantic_cache"]["status"] == "fail"
    assert gates["invalid_req_id"]["status"] == "pass"


def test_compat_rejects_hub_port() -> None:
    out = compat_check(HelperConfig(zeus_url="http://localhost:9091"))
    assert out["ok"] is False
    assert out["zeus_version"] is None
    assert out["client_floor"] == CLIENT_FLOOR
    assert "COMPAT" not in out or "triple" not in str(out.get("docs"))
    ids = [g["id"] for g in out["gates"]]
    assert "public_port" in ids
    # never a fake COMPAT row
    assert "compat" not in out
    assert out["docs"]["COMPAT_0.7"]
    assert "not a published COMPAT" in out["docs"]["note"].lower() or "not a published" in out["docs"]["note"]


def test_compat_missing_url() -> None:
    out = compat_check(HelperConfig(zeus_url=""))
    assert out["ok"] is False
    assert out["zeus_version"] is None
    assert out["client_floor"] == CLIENT_FLOOR
