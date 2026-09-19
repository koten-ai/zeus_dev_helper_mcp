#!/usr/bin/env python3
"""GET key published Zeus Client docs pages; fail on HTTP 404 (ZDM-10).

Not wired into CI (network flake risk). Run manually:

  python scripts/docs_link_smoke.py
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

PAGES = (
    "https://docs.koten.ai/zeus-client",
    "https://docs.koten.ai/zeus-client/for-ai-agents",
    "https://docs.koten.ai/zeus-client/dev-helper-mcp",
    "https://docs.koten.ai/zeus-client/errors",
    "https://docs.koten.ai/zeus-client/start",
    "https://docs.koten.ai/zeus-client/using-zeus-client",
)


def _status(url: str, timeout: float = 15.0) -> int:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "zeus-dev-helper-docs-smoke/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — public docs only
            return int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as e:
        return int(e.code)


def main() -> int:
    failed = 0
    for url in PAGES:
        code = _status(url)
        ok = code < 400 and code != 404
        print(f"{code}\t{url}")
        if not ok:
            failed += 1
    if failed:
        print(f"FAILED: {failed} page(s) returned error/404", file=sys.stderr)
        return 1
    print(f"OK: {len(PAGES)} pages reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
