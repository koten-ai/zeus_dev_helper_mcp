"""yelp-demo app creation downloads the public business photo set."""

from __future__ import annotations

import json
import subprocess
import urllib.error
from pathlib import Path
from typing import Self

import pytest

from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.yelp import ensure_yelp_sample
from zeus_dev_helper_mcp.yelp_images import apply_yelp_business_images, image_slug

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

    def __enter__(self) -> Self:
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


def _write_catalog(root: Path, data: object) -> Path:
    path = root / "frontend" / "src" / "data"
    path.mkdir(parents=True, exist_ok=True)
    catalog = path / "catalog.json"
    catalog.write_text(json.dumps(data), encoding="utf-8")
    return catalog


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "err", None, None)


def test_image_slug_strips_biz_prefixes() -> None:
    assert image_slug("biz:yelp:XYZ") == "XYZ"
    assert image_slug(" biz:ABC ") == "ABC"
    assert image_slug("/biz:ABC/") == "ABC"
    assert image_slug("plain") == "plain"
    assert image_slug(None) == ""
    assert image_slug("biz:yelp:") == ""


@pytest.mark.parametrize("flag", ["1", "true", "yes", " true "])
def test_skip_env_leaves_the_catalog(tmp_path: Path, monkeypatch, flag: str) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    catalog = _write_catalog(
        root,
        [{"business_id": "biz:ABC123", "image": "/business-images/biz:ABC123/1.png"}],
    )
    before = catalog.read_text(encoding="utf-8")
    monkeypatch.setenv("ZEUS_DEV_HELPER_SKIP_YELP_IMAGES", flag)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    report = apply_yelp_business_images(root)
    assert report["skipped"] is True
    assert report["reason"] == "ZEUS_DEV_HELPER_SKIP_YELP_IMAGES"
    assert report["ok"] is True
    assert catalog.read_text(encoding="utf-8") == before


def test_bad_catalog_json_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    catalog = _write_catalog(root, [])
    catalog.write_text("{", encoding="utf-8")
    report = apply_yelp_business_images(root)
    assert report["ok"] is False
    assert report["errors"] == ["catalog:JSONDecodeError"]
    assert report["downloaded"] == 0


def test_catalog_without_business_image_paths_skips(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _write_catalog(
        root,
        [
            "nope",
            {
                "business_id": "biz:ABC",
                "name": "Cafe",
                "image": "https://example.com/a.jpg",
            },
            {"business_id": "biz:yelp:", "image": "/business-images/biz:yelp:/1.png"},
        ],
    )
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    report = apply_yelp_business_images(root)
    assert report["ok"] is True
    assert report["skipped"] is True
    assert report["reason"] == "catalog has no business image paths"
    assert report["rewritten_paths"] == 0


def test_non_list_catalog_skips(tmp_path: Path) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _write_catalog(root, {"businesses": []})
    report = apply_yelp_business_images(root)
    assert report["skipped"] is True
    assert report["reason"] == "catalog has no business image paths"


def test_biz_yelp_prefix_downloads_under_the_bare_id(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _write_catalog(
        root,
        [
            {
                "business_id": "biz:yelp:XYZ",
                "image": "/business-images/biz:yelp:XYZ/1.png",
                "images": ["/business-images/biz:yelp:XYZ/1.png"],
            }
        ],
    )
    seen: list[str] = []

    def fake_urlopen(req, timeout=0):
        seen.append(getattr(req, "full_url", str(req)))
        return _Body(PNG)

    monkeypatch.setenv("BUSINESS_IMAGES_BASE_URL", "http://photos.test/")
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen", fake_urlopen
    )
    report = apply_yelp_business_images(root)
    assert report["ok"] is True
    assert report["source"] == "http://photos.test"
    assert report["downloaded"] == 1
    assert report["businesses"] == 1
    assert seen[0] == "http://photos.test/biz:XYZ/1.png"
    catalog = json.loads(
        (root / "frontend/src/data/catalog.json").read_text(encoding="utf-8")
    )
    assert catalog[0]["business_id"] == "biz:yelp:XYZ"
    assert catalog[0]["image"] == "/business-images/XYZ/1.png"
    assert (root / "frontend/public/business-images/XYZ/1.png").is_file()


def test_download_falls_back_when_the_biz_object_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _write_catalog(
        root,
        [{"business_id": "biz:ABC123", "image": "/business-images/biz:ABC123/1.png"}],
    )
    seen: list[str] = []

    def fake_urlopen(req, timeout=0):
        url = getattr(req, "full_url", str(req))
        seen.append(url)
        if "/biz:" in url:
            raise _http_error(url, 404)
        return _Body(PNG)

    monkeypatch.setenv("BUSINESS_IMAGES_BASE_URL", "http://photos.test")
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen", fake_urlopen
    )
    report = apply_yelp_business_images(root)
    assert report["ok"] is True
    assert report["downloaded"] == 1
    assert seen == [
        "http://photos.test/biz:ABC123/1.png",
        "http://photos.test/ABC123/1.png",
    ]


def test_http_error_other_than_404_stops(
    tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _write_catalog(
        root,
        [{"business_id": "biz:ABC123", "image": "/business-images/biz:ABC123/1.png"}],
    )
    seen: list[str] = []

    def fake_urlopen(req, timeout=0):
        url = getattr(req, "full_url", str(req))
        seen.append(url)
        raise _http_error(url, 500)

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen", fake_urlopen
    )
    report = apply_yelp_business_images(root)
    assert report["ok"] is False
    assert report["failed"] == 1
    assert report["errors"] == ["ABC123/1.png:http_500"]
    assert len(seen) == 3
    assert not (root / "frontend/public/business-images/ABC123/1.png").exists()
    assert "yelp photos 1/1 failed=1" in capsys.readouterr().err


def test_403_and_connection_errors_are_retried(
    tmp_path: Path, monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _write_catalog(
        root,
        [{"business_id": "biz:ABC123", "image": "/business-images/biz:ABC123/1.png"}],
    )
    seen: list[str] = []

    def fake_urlopen(req, timeout=0):
        url = getattr(req, "full_url", str(req))
        seen.append(url)
        if len(seen) == 1:
            raise _http_error(url, 403)
        if len(seen) == 2:
            raise ConnectionError("dropped")
        return _Body(PNG)

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen", fake_urlopen
    )
    report = apply_yelp_business_images(root)
    assert report["ok"] is True
    assert report["downloaded"] == 1
    assert len(seen) == 3
    assert (root / "frontend/public/business-images/ABC123/1.png").is_file()
    assert "yelp photos 1/1 failed=0" in capsys.readouterr().err


def test_bad_bytes_and_fetch_errors_are_counted(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    catalog = _write_catalog(
        root,
        [
            {
                "business_id": "biz:ABC123",
                "image": "/business-images/biz:ABC123/1.png",
                "images": [
                    "/business-images/biz:ABC123/1.png",
                    "/business-images/biz:ABC123/2.png",
                ],
            }
        ],
    )

    def fake_urlopen(req, timeout=0):
        url = getattr(req, "full_url", str(req))
        if url.endswith("/1.png"):
            return _Body(b"nope" * 10)
        raise TimeoutError("slow")

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen", fake_urlopen
    )
    report = apply_yelp_business_images(root)
    assert report["ok"] is False
    assert report["failed"] == 2
    assert report["downloaded"] == 0
    assert "ABC123/1.png:bad:40" in report["errors"]
    assert "ABC123/2.png:TimeoutError" in report["errors"]
    saved = json.loads(catalog.read_text(encoding="utf-8"))
    assert saved[0]["business_id"] == "biz:ABC123"
    assert saved[0]["image"] == "/business-images/ABC123/1.png"
    manifest = json.loads(
        (root / "frontend/public/business-images/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["businesses"] == {}


def test_small_or_non_png_file_is_downloaded_again(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _catalog(root)
    images = root / "frontend/public/business-images/ABC123"
    images.mkdir(parents=True)
    (images / "1.png").write_bytes(b"tiny")
    (images / "2.png").write_bytes(b"x" * 1200)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda req, timeout=0: _Body(PNG),
    )
    report = apply_yelp_business_images(root)
    assert report["downloaded"] == 2
    assert report["already_present"] == 0
    assert (images / "1.png").read_bytes().startswith(b"\x89PNG")
    assert (images / "2.png").read_bytes().startswith(b"\x89PNG")


def test_prefixed_dir_is_kept_when_the_bare_dir_exists(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _catalog(root)
    bare = root / "frontend/public/business-images/ABC123"
    prefixed = root / "frontend/public/business-images/biz:ABC123"
    bare.mkdir(parents=True)
    prefixed.mkdir()
    (bare / "1.png").write_bytes(PNG)
    (bare / "2.png").write_bytes(PNG)
    (prefixed / "1.png").write_bytes(PNG)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")),
    )
    report = apply_yelp_business_images(root)
    assert report["renamed_dirs"] == 0
    assert report["already_present"] == 2
    assert report["downloaded"] == 0
    assert prefixed.is_dir()


def test_already_bare_paths_are_not_rewritten(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    data = [
        {
            "business_id": "ABC123",
            "image": "/business-images/ABC123/1.png",
            "images": ["/business-images/ABC123/1.png"],
        }
    ]
    catalog = _write_catalog(root, data)
    raw = catalog.read_text(encoding="utf-8")
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda req, timeout=0: _Body(PNG),
    )
    report = apply_yelp_business_images(root)
    assert report["rewritten_paths"] == 0
    assert report["downloaded"] == 1
    assert catalog.read_text(encoding="utf-8") == raw


def test_jpeg_bytes_are_stored_as_png(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _write_catalog(
        root,
        [{"business_id": "ABC123", "image": "/business-images/ABC123/1.png"}],
    )
    jpeg = b"\xff\xd8\xff" + b"\x00" * 1200

    def fake_sips(cmd, check, capture_output):
        dest = Path(cmd[cmd.index("--out") + 1])
        dest.write_bytes(PNG)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda req, timeout=0: _Body(jpeg),
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp_images.subprocess.run", fake_sips)
    report = apply_yelp_business_images(root)
    dest = root / "frontend/public/business-images/ABC123/1.png"
    assert report["ok"] is True
    assert report["downloaded"] == 1
    assert dest.read_bytes().startswith(b"\x89PNG")
    assert not dest.with_name("1.src.jpg").exists()


def test_png_conversion_failure_is_counted(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _write_catalog(
        root,
        [{"business_id": "ABC123", "image": "/business-images/ABC123/1.png"}],
    )
    jpeg = b"\xff\xd8\xff" + b"\x00" * 1200

    def fake_sips(cmd, check, capture_output):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda req, timeout=0: _Body(jpeg),
    )
    monkeypatch.setattr("zeus_dev_helper_mcp.yelp_images.subprocess.run", fake_sips)
    report = apply_yelp_business_images(root)
    assert report["ok"] is False
    assert report["failed"] == 1
    assert report["errors"] == ["ABC123/1.png:CalledProcessError"]
    images = root / "frontend/public/business-images/ABC123"
    assert not (images / "1.src.jpg").exists()


def test_failed_downloads_stay_in_the_next_action(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "demo_yelp"
    _layout(root)
    _catalog(root)
    monkeypatch.delenv("DEMO_YELP_SAMPLE_DIR", raising=False)
    monkeypatch.setattr(
        "zeus_dev_helper_mcp.yelp_images.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(TimeoutError("down")),
    )
    out = ensure_yelp_sample(_cfg(tmp_path), sample_dir=str(root))
    assert out["ok"] is True
    assert out["images"]["ok"] is False
    assert out["images"]["failed"] == 2
    catalog = json.loads(
        (root / "frontend/src/data/catalog.json").read_text(encoding="utf-8")
    )
    assert catalog[0]["image"] == "/business-images/ABC123/1.png"
    assert "2 photo download(s) failed." in out["next_action"]
    assert "no API key" in out["next_action"]
