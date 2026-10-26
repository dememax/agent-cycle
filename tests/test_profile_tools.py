# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Integration tests for project profiles in the stateful tools — agent-cycle project

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from .conftest import PYTHON, ROOT, IsolatedEnvironment
from .rollout import task_complete, write_records
from .test_audit import assistant_message, tool_call, write_schema
from .test_identifier import SINCE, candidate_path, make_old_log, valid_records
from .test_queue import PROMPT

if TYPE_CHECKING:
    from pathlib import Path

IDENTIFIER = ROOT / "bin" / "codex-identify-thread.py"
QUEUE = ROOT / "bin" / "codex-queue-turn.sh"
AUDIT = ROOT / "bin" / "audit-turn.py"
RETIRED_VARIABLES = ("AGENT_CYCLE_REPO", "AGENT_CYCLE_STATE", "S0_STATE_DIR")


def tool_command(tool: str, tmp_path: Path) -> list[str | Path]:
    """Return a no-write invocation that reaches profile loading first."""
    if tool == "identifier":
        return [PYTHON, "-I", IDENTIFIER]
    if tool == "queue":
        return [QUEUE, tmp_path / "absent-turn"]
    return [PYTHON, "-I", AUDIT, tmp_path / "absent-log", "0", tmp_path / "absent-schema", tmp_path / "output"]


def run_configuration_case(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    tool: str,
    *,
    extra_env: dict[str, str] | None = None,
    unset_env: tuple[str, ...] = RETIRED_VARIABLES,
) -> tuple[int, str, str]:
    """Run one stateful tool with a controlled project environment."""
    before = set(tmp_path.rglob("*"))
    result = isolated_env.run(
        tool_command(tool, tmp_path),
        extra_env=extra_env,
        unset_env=unset_env,
    )
    assert set(tmp_path.rglob("*")) == before
    return result.returncode, result.stdout, result.stderr


@pytest.mark.parametrize("tool", ["identifier", "queue", "audit"])
@pytest.mark.parametrize("value", [None, "", "relative/profile.toml"], ids=["unset", "empty", "relative"])
def test_each_stateful_tool_requires_an_absolute_profile_selector(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    tool: str,
    value: str | None,
) -> None:
    """No stateful entry point has a default or searches for a profile."""
    extra_env = {} if value is None else {"AGENT_CYCLE_PROFILE": value}
    unset_env = (*RETIRED_VARIABLES, "AGENT_CYCLE_PROFILE") if value is None else RETIRED_VARIABLES

    code, stdout, stderr = run_configuration_case(
        isolated_env,
        tmp_path,
        tool,
        extra_env=extra_env,
        unset_env=unset_env,
    )

    assert code == 2
    assert stdout == ""
    prefix = {"identifier": "codex-identify-thread", "queue": "codex-queue-turn", "audit": "audit-turn"}[tool]
    assert stderr.startswith(prefix)
    assert stderr.count("\n") == 1
    assert "AGENT_CYCLE_PROFILE" in stderr


@pytest.mark.parametrize("tool", ["identifier", "queue", "audit"])
@pytest.mark.parametrize("variable", RETIRED_VARIABLES)
def test_each_stateful_tool_refuses_each_retired_selector(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    tool: str,
    variable: str,
) -> None:
    """A stale project variable cannot be ignored by any stateful tool."""
    code, stdout, stderr = run_configuration_case(
        isolated_env,
        tmp_path,
        tool,
        extra_env={variable: "/generated/stale"},
        unset_env=tuple(item for item in RETIRED_VARIABLES if item != variable),
    )

    assert code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert variable in stderr
    assert "retired" in stderr


@pytest.mark.parametrize("tool", ["identifier", "queue", "audit"])
def test_each_stateful_tool_refuses_invalid_profile(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    tool: str,
) -> None:
    """Every entry point renders loader failures as one configuration line."""
    isolated_env.profile.write_text("profile_version = [\n", encoding="utf-8")

    code, stdout, stderr = run_configuration_case(isolated_env, tmp_path, tool)

    assert code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert str(isolated_env.profile) in stderr
    assert "invalid TOML" in stderr


def test_queue_refuses_noncanonical_profile_path(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """A stateful tool reports a lexical path error before touching state."""
    isolated_env.profile.write_text(
        f'profile_version = 1\nname = "x"\nrepository = "/generated//repo"\nstate = "{isolated_env.state}"\n',
        encoding="utf-8",
    )

    code, stdout, stderr = run_configuration_case(isolated_env, tmp_path, "queue")

    assert code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert str(isolated_env.profile) in stderr
    assert "repository" in stderr
    assert 'expected a canonical path (no empty, "." or ".." component, no trailing "/")' in stderr


def test_identifier_and_queue_use_the_same_profile_state(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Identification writes the exact state directory that queueing reads."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    candidate = candidate_path(isolated_env)
    write_records(candidate, valid_records(thread_id="thread-profile", cwd=isolated_env.repo))
    identifier = isolated_env.run(
        [PYTHON, "-I", IDENTIFIER, "generated orientation sentinel", SINCE, old_log, "--write"],
        unset_env=RETIRED_VARIABLES,
    )
    assert identifier.returncode == 0, identifier.stderr
    active = isolated_env.state / "active-codex-thread.json"
    assert json.loads(active.read_text(encoding="utf-8"))["cwd"] == str(isolated_env.repo)

    turn_dir = tmp_path / "turn-profile"
    turn_dir.mkdir()
    (turn_dir / "prompt.md").write_text(PROMPT, encoding="utf-8")
    queued = isolated_env.run(
        [QUEUE, turn_dir],
        extra_env={
            "FAKE_CODEX_MODE": "turn",
            "FAKE_CODEX_LOG": str(candidate),
            "FAKE_CODEX_PROMPT": str(turn_dir / "prompt.md"),
        },
        unset_env=RETIRED_VARIABLES,
    )

    assert queued.returncode == 0, queued.stderr
    assert (isolated_env.state / "queue.lock").is_file()
    assert (turn_dir / "turn-id").read_text(encoding="utf-8") == "turn-new\n"


def test_audit_profile_selects_escalation_repository(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """The profile repository is the audit's only allowed commit workdir."""
    log = tmp_path / "audit.jsonl"
    write_records(
        log,
        [
            tool_call("git add generated.py", str(isolated_env.repo)),
            assistant_message('{"status":"ok"}'),
            task_complete("turn-audit"),
        ],
    )
    schema = tmp_path / "schema.json"
    write_schema(schema)
    output = tmp_path / "audit-output"
    output.mkdir()

    result = isolated_env.run(
        [PYTHON, "-I", AUDIT, log, "0", schema, output],
        unset_env=RETIRED_VARIABLES,
    )

    assert result.returncode == 0, result.stderr
    assert f"ESCALATION ok  [{isolated_env.repo}]" in result.stdout
    assert "result: valid" in result.stdout
