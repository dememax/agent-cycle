# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Strict reader of Codex rollout logs, shared by the tools — agent-cycle project

"""Strict reading of a Codex rollout log, shared by the S0 tools.

Every function fails closed: a malformed line, a missing record or an
ambiguous structure raises ``LogError`` instead of being skipped.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


class ProfileError(ValueError):
    """A project profile cannot be selected or read without guessing."""


@dataclass(frozen=True)
class ValidationStep:
    """One shell-free validation command from a version-2 profile."""

    name: str
    arguments: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]
    pytest: bool
    always_show: bool
    require_clean: bool


@dataclass(frozen=True)
class ProjectProfile:
    """Project paths and optional version-2 validation commands."""

    name: str
    repository: Path
    state: Path
    validation: tuple[ValidationStep, ...] = ()


PROFILE_KEYS = frozenset(("profile_version", "name", "repository", "state"))
VALIDATION_KEYS = frozenset(("name", "arguments", "environment", "pytest", "always_show", "require_clean"))
RETIRED_PROFILE_VARIABLES = ("AGENT_CYCLE_REPO", "AGENT_CYCLE_STATE", "S0_STATE_DIR")


def _require_canonical_path_spelling(profile_path: Path, key: str, value: str, relative_part: str) -> None:
    """Reject lexical path components that Path would silently normalize."""
    if value.endswith("/") or any(component in ("", ".", "..") for component in relative_part.split("/")):
        raise ProfileError(
            f'{profile_path}: {key}: expected a canonical path (no empty, "." or ".." component, no trailing "/")'
        )


def _profile_value_path(profile_path: Path, key: str, value: object) -> Path:
    """Validate and expand one path from a selected profile."""
    if not isinstance(value, str):
        raise ProfileError(f"{profile_path}: {key}: expected a string path")
    if value.startswith("~/"):
        _require_canonical_path_spelling(profile_path, key, value, value[2:])
        home = os.environ.get("HOME")
        if not home or not Path(home).is_absolute():
            raise ProfileError(f"{profile_path}: {key}: cannot expand ~/ because HOME is not absolute")
        return Path(home) / value[2:]
    path = Path(value)
    if not path.is_absolute():
        raise ProfileError(f"{profile_path}: {key}: expected absolute or starting with ~/")
    _require_canonical_path_spelling(profile_path, key, value, value[1:])
    return path


def _validation_flag(profile_path: Path, index: int, step: dict[str, Any], key: str) -> bool:
    """Read one optional boolean validation flag without accepting integers."""
    value = step.get(key, False)
    if type(value) is not bool:
        raise ProfileError(f"{profile_path}: validation[{index}].{key}: expected a boolean")
    return value


def _validation_steps(profile_path: Path, value: object) -> tuple[ValidationStep, ...]:
    """Validate the exact version-2 validation-step grammar."""
    if not isinstance(value, list) or not value:
        raise ProfileError(f"{profile_path}: validation: expected a non-empty array of tables")
    parsed = []
    names: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ProfileError(f"{profile_path}: validation[{index}]: expected a table")
        unknown = item.keys() - VALIDATION_KEYS
        if unknown:
            key = sorted(unknown)[0]
            raise ProfileError(f"{profile_path}: validation[{index}].{key}: unknown key")
        for key in ("name", "arguments"):
            if key not in item:
                raise ProfileError(f"{profile_path}: validation[{index}].{key}: missing required key")
        name = item["name"]
        if not isinstance(name, str) or not name:
            raise ProfileError(f"{profile_path}: validation[{index}].name: expected a non-empty string")
        if name in names:
            raise ProfileError(f"{profile_path}: validation[{index}].name: duplicate name {name!r}")
        names.add(name)
        arguments = item["arguments"]
        if (
            not isinstance(arguments, list)
            or not arguments
            or any(not isinstance(argument, str) or not argument for argument in arguments)
        ):
            raise ProfileError(
                f"{profile_path}: validation[{index}].arguments: expected a non-empty array of non-empty strings"
            )
        environment = item.get("environment", {})
        if not isinstance(environment, dict) or any(
            not isinstance(key, str)
            or not key
            or "=" in key
            or "\0" in key
            or not isinstance(environment_value, str)
            or "\0" in environment_value
            for key, environment_value in environment.items()
        ):
            raise ProfileError(
                f"{profile_path}: validation[{index}].environment: expected valid string environment entries"
            )
        parsed.append(
            ValidationStep(
                name=name,
                arguments=tuple(arguments),
                environment=tuple(environment.items()),
                pytest=_validation_flag(profile_path, index, item, "pytest"),
                always_show=_validation_flag(profile_path, index, item, "always_show"),
                require_clean=_validation_flag(profile_path, index, item, "require_clean"),
            )
        )
    return tuple(parsed)


def load_project_profile() -> ProjectProfile:
    """Load the required exact version-1 or version-2 selected profile."""
    for variable in RETIRED_PROFILE_VARIABLES:
        if variable in os.environ:
            raise ProfileError(f"{variable}: retired; unset it and use AGENT_CYCLE_PROFILE")
    if "AGENT_CYCLE_PROFILE" not in os.environ:
        raise ProfileError("AGENT_CYCLE_PROFILE: is unset")
    selected = os.environ["AGENT_CYCLE_PROFILE"]
    profile_path = Path(selected)
    if not profile_path.is_absolute():
        raise ProfileError(f"AGENT_CYCLE_PROFILE: must be an absolute path, not {selected!r}")
    try:
        with profile_path.open("rb") as stream:
            profile = tomllib.load(stream)
    except OSError as error:
        raise ProfileError(f"{profile_path}: profile: cannot read ({error})") from None
    except tomllib.TOMLDecodeError as error:
        raise ProfileError(f"{profile_path}: profile: invalid TOML ({error})") from None
    if "profile_version" not in profile:
        raise ProfileError(f"{profile_path}: profile_version: missing required key")
    version = profile["profile_version"]
    if type(version) is not int or version not in (1, 2):
        raise ProfileError(f"{profile_path}: profile_version: expected integer 1 or 2")
    keys = PROFILE_KEYS if version == 1 else PROFILE_KEYS | {"validation"}
    missing = keys - profile.keys()
    if missing:
        key = sorted(missing)[0]
        raise ProfileError(f"{profile_path}: {key}: missing required key")
    unknown = profile.keys() - keys
    if unknown:
        key = sorted(unknown)[0]
        raise ProfileError(f"{profile_path}: {key}: unknown key")
    name = profile["name"]
    if not isinstance(name, str) or not name:
        raise ProfileError(f"{profile_path}: name: expected a non-empty string")
    return ProjectProfile(
        name=name,
        repository=_profile_value_path(profile_path, "repository", profile["repository"]),
        state=_profile_value_path(profile_path, "state", profile["state"]),
        validation=_validation_steps(profile_path, profile["validation"]) if version == 2 else (),
    )


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


def records(path: Path) -> list[dict[str, Any]]:
    """Every line must be one JSON object; nothing is skipped."""
    out: list[dict[str, Any]] = []
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


def session_meta(recs: list[dict[str, Any]]) -> dict[str, Any]:
    first = recs[0]
    if first.get("type") != "session_meta":
        raise LogError("first record is not session_meta")
    return first.get("payload") or {}


def composer_messages(recs: list[dict[str, Any]]) -> list[tuple[int, str, str]]:
    """(index, turn_id, text) of each composer message, in log order.

    A composer message is a user-role response item whose metadata
    ``content_item_kinds`` is exactly ["user.text"]; injected items
    (AGENTS.md, environment, app state) carry other kinds.
    """
    out: list[tuple[int, str, str]] = []
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
        out.append((index, cast("str", meta.get("turn_id")), text))
    return out


def turn_states(recs: list[dict[str, Any]]) -> dict[str, dict[str, int | None]]:
    """Per turn ID: index of task_started and of its later task_complete."""
    states: dict[str, dict[str, int | None]] = {}
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


def running_turns(recs: list[dict[str, Any]]) -> list[str]:
    return [turn for turn, state in turn_states(recs).items() if state["complete"] is None]


def initial_composer(recs: list[dict[str, Any]]) -> tuple[str, str]:
    """(turn_id, text) of the thread's first composer message; its turn must be complete."""
    messages = composer_messages(recs)
    if not messages:
        raise LogError("no composer message")
    _index, turn, text = messages[0]
    states = turn_states(recs)
    if turn not in states or states[turn]["complete"] is None:
        raise LogError("the initial composer turn is not complete")
    return turn, text


def turn_contexts(recs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r.get("payload") or {} for r in recs if r.get("type") == "turn_context"]
