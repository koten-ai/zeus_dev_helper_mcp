from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.diagnose import diagnose_error


def test_diagnose_409() -> None:
    out = diagnose_error(HelperConfig(), status="409", message="contract drift")
    assert out["failure_class"] == "hash_drift"
    assert out["doc_anchor"] == "err-409-drift"


def test_diagnose_wrong_port() -> None:
    out = diagnose_error(HelperConfig(), zeus_url="http://localhost:9091")
    assert out["failure_class"] == "wrong_port_hub_vs_public"


def test_diagnose_401() -> None:
    out = diagnose_error(HelperConfig(), status="401", body="unauthorized")
    assert out["failure_class"] == "auth_failed"
