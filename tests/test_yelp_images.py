"""yelp-demo app creation downloads the public business photo set."""

from __future__ import annotations

import json
from pathlib import Path

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.yelp import ensure_yelp_sample
from zeus_dev_helper_mcp.yelp_images import apply_yelp_business_images


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 1200


def _cfg(tmp_path: Path) -> HelperConfig:
    return HelperConfig(state_dir=tmp_path / "state")


def _layout(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "README.md").write_text("# yelp\n", encoding="utf-8")
    frontend = dest / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")


def _catalog(root: Path) -> None:
    data = [
        {
            "business_id": "biz:ABC123",
            "name": "Cafe",
            "image": "/business-images/biz:ABC123/1.png",
            "images": [
                "/business-images/biz:ABC123/1.png",
                "/business-images/biz:ABC123/2.png",
            ],
        }
    ]
    path = root / "frontend" / "src" / "data"
    path.mkdir(parents=True)
    (path / "catalog.json").write_text(json.dumps(data), encoding="utf-8")


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_Body":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def test_apply_downloads_bare_id_and_strips_biz_prefix(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _catalog(root)
    seen: list[str] = []

    def fake_urlopen(req, timeout=0):
        url = getattr(req, "full_url", str(req))
        seen.append(url)
        return _Body(PNG)

    monkeypatch.setattr("zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen", fake_urlopen)
    report = apply_yelp_business_images(root)
    assert report["ok"] is True
    assert report["api_key"] is False
    assert report["downloaded"] == 2
    assert report["failed"] == 0
    assert report["rewritten_paths"] == 3
    assert all("/biz:ABC123/" in url for url in seen)
    catalog = json.loads((root / "frontend/src/data/catalog.json").read_text(encoding="utf-8"))
    assert catalog[0]["business_id"] == "biz:ABC123"
    assert catalog[0]["image"] == "/business-images/ABC123/1.png"
    assert (root / "frontend/public/business-images/ABC123/1.png").read_bytes().startswith(b"\x89PNG")
    manifest = json.loads(
        (root / "frontend/public/business-images/manifest.json").read_text(encoding="utf-8")
    )
    assert "ABC123" in manifest["businesses"]
    assert "biz:ABC123" not in manifest["businesses"]
    again = apply_yelp_business_images(root)
    assert again["downloaded"] == 0
    assert again["already_present"] == 2
    assert again["ok"] is True


def test_apply_renames_existing_biz_directory(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _catalog(root)
    old = root / "frontend/public/business-images/biz:ABC123"
    old.mkdir(parents=True)
    (old / "1.png").write_bytes(PNG)
    (old / "2.png").write_bytes(PNG)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    report = apply_yelp_business_images(root)
    assert report["renamed_dirs"] == 1
    assert report["already_present"] == 2
    assert report["downloaded"] == 0
    assert (root / "frontend/public/business-images/ABC123/1.png").is_file()
    assert not old.exists()


def test_ensure_without_catalog_skips_photos(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    monkeypatch.delenv("DEMO_YELP_SAMPLE_DIR", raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    out = ensure_yelp_sample(_cfg(tmp_path), sample_dir=str(root))
    assert out["ok"] is True
    assert out["images"]["skipped"] is True
    assert out["images"]["reason"] == "no catalog"
    assert "No API key" not in out["next_action"]


def test_ensure_reports_photos(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _catalog(root)
    monkeypatch.delenv("DEMO_YELP_SAMPLE_DIR", raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda req, timeout=0: _Body(PNG),
    )
    out = ensure_yelp_sample(_cfg(tmp_path), sample_dir=str(root))
    assert out["ok"] is True
    assert out["images"]["downloaded"] == 2
    assert "frontend/public/business-images/<id>/" in out["next_action"]
    assert "no API key" in out["next_action"]
