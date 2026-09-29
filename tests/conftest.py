"""Isolate process env that beer writes leave behind for later tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_recorded_beer_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEMO_BEER_SAMPLE_DIR", raising=False)
