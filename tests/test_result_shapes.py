"""ZDM-17: generated catalog UI follows live V2 find and search shapes."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
from pathlib import Path

from zeus_dev_helper_mcp.beer import (
    catalog_find_body,
    list_range_label,
    list_total,
    offset_page_differs,
    search_hit_state,
    write_beer_sample,
)
from zeus_dev_helper_mcp.config import HelperConfig
from zeus_dev_helper_mcp.walkthrough import RESULT_SHAPES, enriched_next_step


def test_list_total_keeps_null_and_zero() -> None:
    assert list_total(None) is None
    assert list_total("10") is None
    assert list_total(True) is None
    assert list_total(0) == 0
    assert list_total(10.9) == 10


def test_missing_total_label_is_shown_range() -> None:
    label = list_range_label(count=10, total=None)
    assert label == "1–10 shown"
    assert "of 0" not in label
    assert list_range_label(count=10, total=24, offset=10) == "11–20 of 24"
    assert list_range_label(count=0, total=None) == "0 shown"


def test_offset_probe_needs_different_ids() -> None:
    assert offset_page_differs(["n_friar"], ["n_friar"]) is False
    assert offset_page_differs(["n_1"], ["n_2"]) is True
    assert offset_page_differs([], ["n_2"]) is False
    assert offset_page_differs(["n_1"], []) is False


def test_catalog_find_omits_offset_until_asked() -> None:
    body = catalog_find_body("Beer", 24)
    assert "offset" not in body
    assert body["limit"] == 24
    assert body["order_by"] == "id"
    assert catalog_find_body("Beer", 24, offset=24)["offset"] == 24


def test_doc_key_hit_is_empty_state_not_a_title() -> None:
    hop = {
        "name": "find",
        "result_json": json.dumps(
            {
                "node_ids": [],
                "items": [{"node": {"doc_key": "cains-ipa"}, "score": 1.2}],
            }
        ),
    }
    state = search_hit_state([hop])
    assert state["items"] == []
    assert state["empty_state"] == "fts_doc_key_only"
    blob = json.dumps(state)
    assert "Cains IPA" not in blob
    assert "cains-ipa" not in blob
    assert "find" not in blob


def test_named_row_still_becomes_a_card() -> None:
    state = search_hit_state(
        [{"id": "n_friar", "name": "Friar's Porter", "style": "Porter"}]
    )
    assert state["empty_state"] is None
    assert state["items"][0]["name"] == "Friar's Porter"


def test_generated_tree_matches_live_shapes(tmp_path: Path) -> None:
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    assert out["ok"] is True
    root = Path(out["local_dir"])
    main = (root / "main.py").read_text(encoding="utf-8")
    html = (root / "static" / "index.html").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    ast.parse(main)

    assert "catalog_find_body(entity, cap)" in main
    assert "offset=cap" in main
    assert "_list_checked" in main
    assert "_LIST_CACHE_CAP = 30" in main
    assert "search_hit_state" in main
    assert "fts_doc_key_only" in main
    assert "Number(data.total)" not in html
    assert "if (pagingOn && pageIndex > 1) params.set(\"offset\"" in html
    assert "range_label" in html
    assert "data.paging === true" in html
    assert "1–N shown" in readme
    assert "offset" in readme
    assert "30 seconds" in readme


def test_next_step_includes_result_shapes(tmp_path: Path) -> None:
    out = enriched_next_step(HelperConfig(state_dir=tmp_path / "state"))
    shapes = out["result_shapes"]
    assert shapes == RESULT_SHAPES
    dumped = json.dumps(shapes)
    assert "1–N shown" in shapes["total"]
    assert "doc_key" in shapes["search"]
    assert "page 2" in shapes["find"]
    assert "fts_search.go" not in dumped
    assert "mapFindVerb" not in dumped
    assert "of 0" not in dumped


def test_page_script_hides_null_total_and_unprobed_offset(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        return
    cfg = HelperConfig(state_dir=tmp_path / "state", default_bucket="beer-sample")
    out = write_beer_sample(cfg, tmp_path / "demo_beer_sample")
    html = (Path(out["local_dir"]) / "static" / "index.html").read_text(encoding="utf-8")
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    probe = r"""
const fs = require("fs");
const script = fs.readFileSync(0, "utf8");
function grab(name) {
  const marker = "function " + name + "(";
  const start = script.indexOf(marker);
  if (start < 0) throw new Error("missing " + name);
  let i = script.indexOf("{", start);
  let depth = 0;
  for (let j = i; j < script.length; j += 1) {
    if (script[j] === "{") depth += 1;
    else if (script[j] === "}") {
      depth -= 1;
      if (depth === 0) return script.slice(start, j + 1);
    }
  }
  throw new Error("unclosed " + name);
}
const pager = { hidden: true, innerHTML: "" };
const document = { getElementById() { return pager; } };
const PAGE_SIZE = 24;
let mode = "beers";
let pagingOn = false;
let pageIndex = 2;
let called = "";
function run(url) { called = url; return url; }
eval(grab("rangeLabel"));
eval(grab("pageWindow"));
eval(grab("renderPager"));
eval(grab("loadList"));
const fromServer = rangeLabel({ paged: true, offset: 0, total: null, range_label: "1–10 shown" }, 10);
if (fromServer !== "1–10 shown") throw new Error("range_label ignored: " + fromServer);
const fallback = rangeLabel({ paged: true, offset: 0, total: null }, 10);
if (fallback.includes("of 0") || !fallback.includes("shown")) throw new Error("null total: " + fallback);
renderPager({ paged: true, paging: false, truncated: true, total: null, offset: 0, limit: 24, items: [{ name: "A" }] });
if (!pager.hidden) throw new Error("Next shown before the probe");
pager.hidden = true;
pager.innerHTML = "";
renderPager({ paged: true, paging: true, truncated: true, total: null, offset: 0, limit: 24, items: [{ name: "A" }] });
if (pager.hidden || !pager.innerHTML.includes(">Next<")) throw new Error("Next hidden after a live probe");
loadList();
if (called.includes("offset=")) throw new Error("offset sent before the probe: " + called);
pagingOn = true;
pageIndex = 2;
loadList();
if (!called.includes("offset=24")) throw new Error("offset missing after the probe: " + called);
"""
    proc = subprocess.run(
        [node, "-e", probe],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
