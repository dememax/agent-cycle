# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box characterization of the strict rollout reader — agent-cycle project

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from .conftest import PYTHON, ROOT, IsolatedEnvironment
from .rollout import composer, session_meta, task_complete, task_started, turn_context, write_records

if TYPE_CHECKING:
    from pathlib import Path

PROBE = ROOT / "tests" / "codexlog_probe.py"


def run_probe(
    isolated_env: IsolatedEnvironment,
    operation: str,
    argument: str | Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run one reader operation in an isolated Python process."""
    result = isolated_env.run([PYTHON, "-I", PROBE, operation, argument], extra_env=extra_env)
    return result.returncode, result.stdout, result.stderr


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not JSON}\n", "malformed JSON"),
        ("[]\n", "not an object"),
        ('{"type": "session_meta"}', "incomplete last line"),
        ("", "empty log"),
        ('{"type": "turn_context", "payload": {}}\n', "first record is not session_meta"),
    ],
    ids=["malformed", "non-object", "incomplete", "empty", "wrong-first-record"],
)
def test_strict_reader_refuses_invalid_logs(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    """Malformed or structurally invalid input is never skipped or repaired."""
    log = tmp_path / "rollout.jsonl"
    log.write_text(content, encoding="utf-8")
    operation = "session_meta" if message == "first record is not session_meta" else "records"

    returncode, stdout, stderr = run_probe(isolated_env, operation, log)

    assert returncode != 0
    assert stdout == ""
    assert message in stderr
    assert log.read_text(encoding="utf-8") == content


def test_canonical_removes_only_trailing_newlines(isolated_env: IsolatedEnvironment) -> None:
    """Canonicalization preserves spaces and leading newlines."""
    original = "\n  prompt with trailing spaces  \n\n"
    returncode, stdout, stderr = run_probe(isolated_env, "canonical", original)

    assert returncode == 0, stderr
    assert json.loads(stdout) == "\n  prompt with trailing spaces  "


def test_initial_composer_skips_injected_items(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """The first completed user.text turn wins, not earlier injected context."""
    log = tmp_path / "rollout.jsonl"
    write_records(
        log,
        [
            session_meta(thread_id="thread-generated", cwd=isolated_env.repo),
            composer("turn-injected", "injected", kinds=("environment_context",)),
            task_started("turn-initial"),
            composer(
                "turn-initial",
                "first prompt",
                content=(
                    {"type": "input_text", "text": "first "},
                    {"type": "image", "url": "generated"},
                    {"type": "input_text", "text": "prompt"},
                ),
            ),
            task_complete("turn-initial"),
            task_started("turn-later"),
            composer("turn-later", "later prompt"),
            task_complete("turn-later"),
        ],
    )

    returncode, stdout, stderr = run_probe(isolated_env, "initial", log)

    assert returncode == 0, stderr
    assert json.loads(stdout) == ["turn-initial", "first prompt"]


def test_running_turns_pair_events_by_turn_id(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """Completing one interleaved turn does not hide another running turn."""
    log = tmp_path / "rollout.jsonl"
    write_records(
        log,
        [
            session_meta(thread_id="thread-generated", cwd=isolated_env.repo),
            turn_context(cwd=isolated_env.repo),
            task_started("turn-one"),
            task_started("turn-two"),
            task_complete("turn-one"),
        ],
    )

    returncode, stdout, stderr = run_probe(isolated_env, "running", log)

    assert returncode == 0, stderr
    assert json.loads(stdout) == ["turn-two"]


@pytest.mark.parametrize("variable", ["AGENT_CYCLE_REPO", "AGENT_CYCLE_STATE"])
def test_project_selection_requires_absolute_paths(isolated_env: IsolatedEnvironment, variable: str) -> None:
    """Either relative project-selection path aborts module initialization."""
    returncode, stdout, stderr = run_probe(
        isolated_env,
        "canonical",
        "prompt",
        extra_env={variable: "relative/path"},
    )

    assert returncode != 0
    assert stdout == ""
    assert f"{variable} must be an absolute path" in stderr
