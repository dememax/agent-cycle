# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Strict reader of Codex rollout logs, shared by the tools — agent-cycle project

"""Strict reading of a Codex rollout log, shared by the S0 tools.

Every function fails closed: a malformed line, a missing record or an
ambiguous structure raises ``LogError`` instead of being skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

CWD = str(Path.home() / "github" / "check_rst")
STOPPING_KEYS = (
    "cwd",
    "workspace_roots",
    "approval_policy",
    "approvals_reviewer",
    "sandbox_policy",
    "permission_profile",
    "active_permission_profile",
    "file_system_sandbox_policy",
    "model",
    "effort",
    "collaboration_mode",
    "personality",
)
DIAGNOSTIC_KEYS = ("timezone", "multi_agent_version", "disabled_plugin_ids")


class LogError(Exception):
    pass


class IncompleteLastLine(LogError):
    """The last line has no newline yet: the log may still be being written."""


def canonical(text: str) -> str:
    """The comparison form of a composer text: trailing newlines removed, nothing else.

    A shell's command substitution drops a prompt's final newline; every
    other character, including leading or trailing spaces, must match.
    """
    return text.rstrip("\n")


def records(path: Path) -> list[dict]:
    """Every line must be one JSON object; nothing is skipped."""
    out: list[dict] = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.endswith("\n"):
                raise IncompleteLastLine(f"{path}:{number}: incomplete last line")
            try:
                record = json.loads(line)
            except ValueError as error:
                raise LogError(f"{path}:{number}: malformed JSON ({error})") from None
            if not isinstance(record, dict):
                raise LogError(f"{path}:{number}: not an object")
            out.append(record)
    if not out:
        raise LogError(f"{path}: empty log")
    return out


def session_meta(recs: list[dict]) -> dict:
    first = recs[0]
    if first.get("type") != "session_meta":
        raise LogError("first record is not session_meta")
    return first.get("payload") or {}


def composer_messages(recs: list[dict]) -> list[tuple[int, str, str]]:
    """(index, turn_id, text) of each composer message, in log order.

    A composer message is a user-role response item whose metadata
    ``content_item_kinds`` is exactly ["user.text"]; injected items
    (AGENTS.md, environment, app state) carry other kinds.
    """
    out = []
    for index, record in enumerate(recs):
        payload = record.get("payload") or {}
        if record.get("type") != "response_item" or payload.get("type") != "message" or payload.get("role") != "user":
            continue
        meta = payload.get("internal_chat_message_metadata_passthrough") or {}
        if meta.get("content_item_kinds") != ["user.text"]:
            continue
        text = "".join(
            part.get("text", "") for part in payload.get("content") or [] if part.get("type") == "input_text"
        )
        out.append((index, meta.get("turn_id"), text))
    return out


def turn_states(recs: list[dict]) -> dict[str, dict]:
    """Per turn ID: index of task_started and of its later task_complete."""
    states: dict[str, dict] = {}
    for index, record in enumerate(recs):
        payload = record.get("payload") or {}
        kind = payload.get("type")
        if record.get("type") != "event_msg" or kind not in ("task_started", "task_complete"):
            continue
        turn = payload.get("turn_id")
        if not turn:
            raise LogError(f"record {index}: {kind} without turn_id")
        state = states.setdefault(turn, {"started": None, "complete": None})
        if kind == "task_started":
            if state["started"] is not None:
                raise LogError(f"turn {turn}: started twice")
            state["started"] = index
        else:
            if state["started"] is None or index < state["started"]:
                raise LogError(f"turn {turn}: complete before start")
            if state["complete"] is not None:
                raise LogError(f"turn {turn}: completed twice")
            state["complete"] = index
    return states


def running_turns(recs: list[dict]) -> list[str]:
    return [turn for turn, state in turn_states(recs).items() if state["complete"] is None]


def initial_composer(recs: list[dict]) -> tuple[str, str]:
    """(turn_id, text) of the thread's first composer message; its turn must be complete."""
    messages = composer_messages(recs)
    if not messages:
        raise LogError("no composer message")
    _index, turn, text = messages[0]
    states = turn_states(recs)
    if turn not in states or states[turn]["complete"] is None:
        raise LogError("the initial composer turn is not complete")
    return turn, text


def turn_contexts(recs: list[dict]) -> list[dict]:
    return [r.get("payload") or {} for r in recs if r.get("type") == "turn_context"]
