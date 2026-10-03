"""Fill business photos when a yelp-demo app is created.

use_sample downloads the public CDN set into
frontend/public/business-images/<id>/{1,2,3}.png. The directory name is the
Yelp id. A leading ``biz:`` or ``biz:yelp:`` is not part of that name.
No API key.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

CDN_BASE = (
    "https://koten-yelp-demo-photos.nyc3.cdn.digitaloceanspaces.com/business-images"
)
CATALOG_REL = Path("frontend/src/data/catalog.json")
IMAGES_REL = Path("frontend/public/business-images")
_MARKER = "/business-images/"
_MIN_BYTES = 1000
_SKIP_ENV = "ZEUS_DEV_HELPER_SKIP_YELP_IMAGES"


def image_slug(business_id: str | None) -> str:
    """Folder name. Drops a leading ``biz:yelp:`` or ``biz:``."""
    bid = (business_id or "").strip().strip("/")
    if bid.startswith("biz:yelp:"):
        return bid[len("biz:yelp:") :]
    if bid.startswith("biz:"):
        return bid[len("biz:") :]
    return bid


def _public_path(slug: str, filename: str) -> str:
    return f"{_MARKER}{slug}/{filename}"


def _normalize_ref(url: str) -> str | None:
    text = (url or "").strip()
    if _MARKER not in text:
        return None
    rest = text.split(_MARKER, 1)[1].lstrip("/")
    folder, sep, name = rest.partition("/")
    if not sep or not name or not folder:
        return None
    slug = image_slug(folder)
    if not slug or not name:
        return None
    return _public_path(slug, name)


def _rewrite_catalog(path: Path) -> tuple[list[str], int]:
    """Point catalog image fields at ``/business-images/<id>/<file>``.

    ``business_id`` stays whatever the template stored. Returns the relative
    paths to download and how many URL strings changed.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return [], 0
    rels: list[str] = []
    seen: set[str] = set()
    changed = 0
    for card in data:
        if not isinstance(card, dict):
            continue
        urls: list[str] = []
        images = card.get("images")
        if isinstance(images, list):
            urls.extend(item for item in images if isinstance(item, str))
        image = card.get("image")
        if isinstance(image, str):
            urls.append(image)
        normalized: list[str] = []
        for url in urls:
            nxt = _normalize_ref(url)
            if not nxt:
                continue
            if nxt != url.strip():
                changed += 1
            if nxt not in normalized:
                normalized.append(nxt)
            rel = nxt.split(_MARKER, 1)[1]
            if rel not in seen:
                seen.add(rel)
                rels.append(rel)
        if normalized:
            card["images"] = normalized
            card["image"] = normalized[0]
    if changed:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return rels, changed


def _rename_prefixed_dirs(images_root: Path) -> int:
    if not images_root.is_dir():
        return 0
    renamed = 0
    for child in list(images_root.iterdir()):
        if not child.is_dir() or not child.name.startswith("biz:"):
            continue
        dest = images_root / image_slug(child.name)
        if dest.exists():
            continue
        child.rename(dest)
        renamed += 1
    return renamed


def _looks_like_image(data: bytes) -> bool:
    if data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8\xff"):
        return True
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return True
    return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "zeus-dev-helper-yelp-images/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _remote_urls(origin: str, rel: str) -> list[str]:
    """CDN objects are published under ``biz:<id>/`` until that tree is re-uploaded."""
    folder, sep, name = rel.partition("/")
    urls = [f"{origin}/{rel}"]
    if sep and name and not folder.startswith("biz:"):
        urls.insert(0, f"{origin}/biz:{folder}/{name}")
    return urls


def _write_png(dest: Path, data: bytes) -> None:
    """Store a real PNG. Some CDN objects named ``*.png`` are JPEG."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if data.startswith(b"\x89PNG"):
        dest.write_bytes(data)
        return
    tmp = dest.with_name(dest.stem + ".src.jpg")
    tmp.write_bytes(data)
    try:
        subprocess.run(
            ["sips", "-s", "format", "png", str(tmp), "--out", str(dest)],
            check=True,
            capture_output=True,
        )
    finally:
        tmp.unlink(missing_ok=True)
    if not dest.is_file() or not dest.read_bytes()[:8].startswith(b"\x89PNG"):
        raise RuntimeError(f"could not store a PNG at {dest.name}")


def _download_one(rel: str, origin: str, images_root: Path) -> tuple[str, str]:
    dest = images_root / rel
    if dest.is_file() and dest.stat().st_size >= _MIN_BYTES:
        if dest.read_bytes()[:8].startswith(b"\x89PNG"):
            return rel, "skip"
    last_error = "not_found"
    for url in _remote_urls(origin, rel):
        try:
            data = _fetch(url)
        except urllib.error.HTTPError as exc:
            last_error = f"http_{exc.code}"
            if exc.code == 404:
                continue
            return rel, last_error
        except Exception as exc:  # noqa: BLE001
            return rel, type(exc).__name__
        if len(data) < _MIN_BYTES or not _looks_like_image(data):
            return rel, f"bad:{len(data)}"
        try:
            _write_png(dest, data)
        except Exception as exc:  # noqa: BLE001
            return rel, type(exc).__name__
        return rel, "ok"
    return rel, last_error


def _write_manifest(images_root: Path, rels: list[str]) -> None:
    grouped: dict[str, list[str]] = {}
    for rel in rels:
        folder, sep, name = rel.partition("/")
        if not sep or not (images_root / rel).is_file():
            continue
        grouped.setdefault(folder, []).append(name)
    businesses: dict[str, dict[str, Any]] = {}
    for slug, names in sorted(grouped.items()):
        files = sorted(names)
        urls = [_public_path(slug, name) for name in files]
        businesses[slug] = {
            "business_id": slug,
            "image": urls[0],
            "images": urls,
            "files": files,
        }
    images_root.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "url_prefix": "/business-images", "businesses": businesses}
    (images_root / "manifest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def apply_yelp_business_images(root: Path) -> dict[str, Any]:
    """Download the public photo set into this yelp checkout.

    Idempotent. A checkout with no bundled catalog is left unchanged.
    A download failure does not remove the catalog rewrite.
    """
    root = root.expanduser().resolve()
    catalog_path = root / CATALOG_REL
    images_root = root / IMAGES_REL
    report: dict[str, Any] = {
        "ok": True,
        "skipped": False,
        "api_key": False,
        "source": CDN_BASE,
        "catalog": CATALOG_REL.as_posix(),
        "dest": IMAGES_REL.as_posix(),
        "rewritten_paths": 0,
        "renamed_dirs": 0,
        "downloaded": 0,
        "already_present": 0,
        "failed": 0,
        "files": 0,
        "businesses": 0,
        "errors": [],
    }
    if os.environ.get(_SKIP_ENV, "").strip() in {"1", "true", "yes"}:
        report["skipped"] = True
        report["reason"] = _SKIP_ENV
        return report
    if not catalog_path.is_file():
        report["skipped"] = True
        report["reason"] = "no catalog"
        return report
    try:
        rels, changed = _rewrite_catalog(catalog_path)
    except (OSError, json.JSONDecodeError) as exc:
        report["ok"] = False
        report["errors"] = [f"catalog:{type(exc).__name__}"]
        return report
    report["rewritten_paths"] = changed
    report["renamed_dirs"] = _rename_prefixed_dirs(images_root)
    if not rels:
        report["skipped"] = True
        report["reason"] = "catalog has no business image paths"
        return report
    origin = (os.environ.get("BUSINESS_IMAGES_BASE_URL") or CDN_BASE).strip().rstrip("/")
    report["source"] = origin
    workers = int(os.environ.get("YELP_IMAGE_FETCH_WORKERS") or "8")
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_download_one, rel, origin, images_root) for rel in rels]
        for fut in as_completed(futures):
            try:
                rel, status = fut.result()
            except Exception as exc:  # noqa: BLE001
                report["failed"] += 1
                if len(errors) < 8:
                    errors.append(type(exc).__name__)
                continue
            if status == "ok":
                report["downloaded"] += 1
            elif status == "skip":
                report["already_present"] += 1
            else:
                report["failed"] += 1
                if len(errors) < 8:
                    errors.append(f"{rel}:{status}")
    report["errors"] = errors
    report["files"] = report["downloaded"] + report["already_present"]
    report["businesses"] = len({rel.partition("/")[0] for rel in rels})
    report["ok"] = report["failed"] == 0
    try:
        _write_manifest(images_root, rels)
    except OSError as exc:
        report["ok"] = False
        if len(errors) < 8:
            errors.append(f"manifest:{type(exc).__name__}")
            report["errors"] = errors
    return report
