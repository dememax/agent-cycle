# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Builders for synthetic Codex rollout records — agent-cycle project

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any

STAMP = "2040-01-02T03:04:05Z"
CLI_VERSION = "0.162.0-alpha.17.2"


def record(record_type: str, payload: Mapping[str, object]) -> dict[str, object]:
    """Build one top-level rollout record."""
    return {"timestamp": STAMP, "type": record_type, "payload": dict(payload)}


def session_meta(
    *,
    thread_id: str,
    cwd: Path,
    source: str = "vscode",
    originator: str = "codex_vscode",
    timestamp: str = STAMP,
    cli_version: str = CLI_VERSION,
) -> dict[str, object]:
    """Build the first record of a generated rollout log."""
    return record(
        "session_meta",
        {
            "id": thread_id,
            "source": source,
            "originator": originator,
            "cwd": str(cwd),
            "timestamp": timestamp,
            "cli_version": cli_version,
        },
    )


def turn_context(*, cwd: Path, **overrides: object) -> dict[str, object]:
    """Build a turn context containing every profile stopping key."""
    payload: dict[str, object] = {
        "cwd": str(cwd),
        "workspace_roots": [str(cwd)],
        "approval_policy": "on-request",
        "approvals_reviewer": "auto_review",
        "sandbox_policy": "workspace-write",
        "permission_profile": "workspace",
        "active_permission_profile": "workspace",
        "file_system_sandbox_policy": {"writable_roots": [str(cwd)]},
        "model": "synthetic-model",
        "effort": "high",
        "collaboration_mode": "default",
        "personality": "pragmatic",
        "timezone": "Etc/UTC",
        "multi_agent_version": "synthetic",
        "disabled_plugin_ids": [],
    }
    payload.update(overrides)
    return record("turn_context", payload)


def turn_context_0164(*, cwd: Path, **overrides: object) -> dict[str, object]:
    """Build the reduced turn-context shape emitted by Codex CLI 0.164."""
    context = turn_context(cwd=cwd, **overrides)
    payload = context["payload"]
    assert isinstance(payload, dict)
    for key in ("personality", "workspace_roots", "timezone"):
        payload.pop(key)
    return context


def thread_settings_applied(*, cwd: Path, **overrides: object) -> dict[str, object]:
    """Build the settings event that supplies profile values outside turn_context."""
    settings: dict[str, object] = {
        "active_permission_profile": "workspace",
        "approval_policy": "on-request",
        "approvals_reviewer": "auto_review",
        "collaboration_mode": "default",
        "cwd": str(cwd),
        "disabled_plugin_ids": [],
        "model": "synthetic-model",
        "model_provider_id": "synthetic-provider",
        "permission_profile": "workspace",
        "personality": "pragmatic",
        "reasoning_effort": "high",
        "reasoning_summary": "auto",
        "runtime_workspace_roots": [str(cwd)],
        "service_tier": "synthetic",
    }
    settings.update(overrides)
    return record(
        "event_msg",
        {"type": "thread_settings_applied", "thread_id": "thread-generated", "thread_settings": settings},
    )


def composer(
    turn_id: str,
    text: str,
    *,
    kinds: Iterable[str] = ("user.text",),
    content: Iterable[Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Build a user response item, either composer-authored or injected."""
    parts = list(content) if content is not None else [{"type": "input_text", "text": text}]
    return record(
        "response_item",
        {
            "type": "message",
            "role": "user",
            "content": parts,
            "internal_chat_message_metadata_passthrough": {
                "turn_id": turn_id,
                "content_item_kinds": list(kinds),
            },
        },
    )


def task_started(turn_id: str) -> dict[str, object]:
    """Build a task-started event."""
    return record("event_msg", {"type": "task_started", "turn_id": turn_id})


def task_complete(turn_id: str) -> dict[str, object]:
    """Build a task-complete event."""
    return record("event_msg", {"type": "task_complete", "turn_id": turn_id})


def token_count(
    *,
    total: Mapping[str, int],
    last: Mapping[str, int],
    primary_used: float,
    secondary_used: float,
) -> dict[str, object]:
    """Build the token and rate-limit shape consumed by turn-usage.py."""
    return record(
        "event_msg",
        {
            "type": "token_count",
            "info": {"total_token_usage": dict(total), "last_token_usage": dict(last)},
            "rate_limits": {
                "limit_id": "codex",
                "primary": {"used_percent": primary_used, "resets_at": 2_208_988_800},
                "secondary": {"used_percent": secondary_used},
            },
        },
    )


def write_records(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    """Write a complete synthetic JSONL log."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{json.dumps(item)}\n" for item in records), encoding="utf-8")


def append_records(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    """Append complete records to a synthetic JSONL log."""
    with path.open("a", encoding="utf-8") as stream:
        for item in records:
            stream.write(f"{json.dumps(item)}\n")
