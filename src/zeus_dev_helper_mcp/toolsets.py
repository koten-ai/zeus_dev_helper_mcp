"""Static Helper toolsets (ZDH-37). Env/flag only — no dynamic enable_toolset."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass

ENV_TOOLSETS = "ZEUS_DEV_HELPER_TOOLSETS"

CORE = "core"
CATALOG = "catalog"
LINT = "lint"
TRAVEL = "travel"
SUPPORT = "support"
HANDOFF = "handoff"
ALL = "all"

NAMED_TOOLSETS = frozenset({CORE, CATALOG, LINT, TRAVEL, SUPPORT, HANDOFF})
CORE_CAP = 15

# name, toolsets (comma), read_only, destructive, idempotent, open_world
_ROWS: tuple[tuple[str, str, bool, bool, bool, bool], ...] = (
    ("doctor", CORE, True, False, True, False),
    ("start_project", CORE, False, True, False, False),
    ("get_checklist", SUPPORT, True, False, True, False),
    ("next_step", CORE, True, False, True, False),
    ("gap_report", SUPPORT, True, False, True, False),
    ("mark_done", SUPPORT, False, False, True, False),
    ("mark_blocked", SUPPORT, False, False, True, False),
    ("validate_env", LINT, True, False, True, False),
    ("set_prereq", CORE, False, False, True, False),
    ("readiness_check", CORE, False, False, True, True),
    ("list_catalog_modes", CATALOG, True, False, True, False),
    ("fetch_chat_request", CATALOG, True, False, True, False),
    ("explain", CATALOG, True, False, True, False),
    ("bootstrap_scope", CATALOG, False, False, True, True),
    ("scaffold_app", CORE, False, True, False, False),
    ("use_sample", CORE, False, False, True, False),
    ("travel_golden_path", TRAVEL, False, False, True, False),
    ("write_env", SUPPORT, False, False, True, False),
    ("verify_local_setup", SUPPORT, True, False, True, False),
    ("smoke_test_zeus", CORE, False, False, False, True),
    ("smoke_test_agent", CORE, False, False, False, True),
    ("diagnose_error", CORE, True, False, True, False),
    ("recommend_surface", CORE, True, False, True, False),
    ("explain_verb", CATALOG, True, False, True, False),
    ("lint_verb_args", f"{CATALOG},{LINT}", True, False, True, False),
    ("suggest_verb_call", f"{CATALOG},{LINT}", True, False, True, False),
    ("compat_check", LINT, True, False, True, True),
    ("lint_chat_request", f"{CATALOG},{LINT}", True, False, True, False),
    ("bind_contract", CORE, True, False, True, False),
    ("explain_hash_boundary", CATALOG, True, False, True, False),
    ("catalog_diff", CATALOG, True, False, True, True),
    ("lint_runtime_config", LINT, True, False, True, False),
    ("lint_app_code", LINT, True, False, True, False),
    ("lint_app", LINT, True, False, True, False),
    ("explain_req_id_policy", SUPPORT, True, False, True, False),
    ("detective_links", SUPPORT, True, False, True, False),
    ("support_pack_from_turn", SUPPORT, True, False, True, False),
    ("describe_scope", CATALOG, True, False, True, True),
    ("recommend_motion", CATALOG, True, False, True, False),
    ("suggest_hooks", SUPPORT, True, False, True, False),
    ("semantic_cache_status", f"{LINT},{SUPPORT}", True, False, True, True),
    ("handoff_to_multi", HANDOFF, True, False, True, False),
    ("recommend_data_plane_mcp", HANDOFF, True, False, True, False),
    ("emit_mcp_config", HANDOFF, True, False, True, False),
    ("helper_metrics", SUPPORT, True, False, True, False),
    ("suggest_demo_prompts", SUPPORT, True, False, True, False),
)


@dataclass(frozen=True)
class ToolMeta:
    name: str
    toolsets: frozenset[str]
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool

    def enabled_for(self, enabled: frozenset[str]) -> bool:
        return bool(self.toolsets & enabled)


TOOL_REGISTRY: tuple[ToolMeta, ...] = tuple(
    ToolMeta(
        name=name,
        toolsets=frozenset(ts for ts in toolsets.split(",") if ts),
        read_only=read_only,
        destructive=destructive,
        idempotent=idempotent,
        open_world=open_world,
    )
    for name, toolsets, read_only, destructive, idempotent, open_world in _ROWS
)

TOOL_META_BY_NAME: dict[str, ToolMeta] = {m.name: m for m in TOOL_REGISTRY}
DEFAULT_CORE_TOOLS: frozenset[str] = frozenset(m.name for m in TOOL_REGISTRY if CORE in m.toolsets)


def parse_toolsets(raw: str | None = None) -> frozenset[str]:
    """Resolve `ZEUS_DEV_HELPER_TOOLSETS`. Default `core`. `all` enables every named set.

    `core` is always included so first-green cannot be switched off by accident.
    """
    if raw is None:
        raw = os.environ.get(ENV_TOOLSETS, CORE)
    parts = {p.strip().lower() for p in (raw or "").split(",") if p.strip()}
    if not parts:
        parts = {CORE}
    if ALL in parts:
        return frozenset(NAMED_TOOLSETS)
    unknown = parts - NAMED_TOOLSETS - {ALL}
    parts -= unknown
    parts.add(CORE)
    return frozenset(parts & NAMED_TOOLSETS)


def enabled_tools(enabled: Iterable[str] | None = None) -> list[ToolMeta]:
    sets = frozenset(enabled) if enabled is not None else parse_toolsets()
    return [m for m in TOOL_REGISTRY if m.enabled_for(sets)]


def default_core_count() -> int:
    return sum(1 for m in TOOL_REGISTRY if CORE in m.toolsets)
