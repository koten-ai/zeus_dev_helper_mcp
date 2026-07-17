from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.scaffold import scaffold_app, use_sample, verify_local_setup


def test_scaffold_writes_files(tmp_path: Path) -> None:
    cfg = HelperConfig(
        zeus_url="http://localhost:8080",
        default_bucket="beer-sample",
        default_scope="_default",
        state_dir=tmp_path / "state",
    )
    out = scaffold_app(cfg, str(tmp_path / "app"), project_name="demo_app")
    assert out["ok"] is True
    root = Path(out["target_dir"])
    assert (root / "main.py").is_file()
    assert (root / "requirements.txt").is_file()
    assert (root / ".env.example").is_file()
    text = (root / "main.py").read_text()
    assert "run_agent" in text
    assert "beer-sample" in text


def test_use_sample_travel(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    out = use_sample(cfg, "travel")
    assert out["ok"] is True
    assert "demo_travel_sample" in out["sample"]["repo"]


def test_verify_local_setup(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state")
    out = verify_local_setup(cfg, str(tmp_path))
    assert "checks" in out
