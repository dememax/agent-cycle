# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box characterization of visible-thread identification — agent-cycle project

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, cast

import pytest

from .conftest import PYTHON, ROOT, IsolatedEnvironment
from .rollout import (
    CLI_VERSION,
    composer,
    session_meta,
    task_complete,
    task_started,
    thread_settings_applied,
    turn_context,
    turn_context_0164,
    write_records,
)
from .test_queue import SENTINEL, STOPPING_KEYS

if TYPE_CHECKING:
    from pathlib import Path

IDENTIFIER = ROOT / "bin" / "codex-identify-thread.py"
SINCE = "2039-01-01T00:00:00+00:00"


def valid_records(*, thread_id: str, cwd: Path, sentinel: str = SENTINEL) -> list[dict[str, object]]:
    """Build one complete candidate rollout."""
    return [
        session_meta(thread_id=thread_id, cwd=cwd),
        turn_context(cwd=cwd),
        task_started("turn-initial"),
        composer("turn-initial", sentinel),
        task_complete("turn-initial"),
    ]


def valid_records_0164(*, thread_id: str, cwd: Path, sentinel: str = SENTINEL) -> list[dict[str, object]]:
    """Build one complete candidate with the Codex CLI 0.164 profile shape."""
    return [
        session_meta(thread_id=thread_id, cwd=cwd),
        task_started("turn-initial"),
        turn_context_0164(cwd=cwd),
        composer("turn-initial", sentinel),
        thread_settings_applied(cwd=cwd),
        task_complete("turn-initial"),
    ]


def make_old_log(tmp_path: Path, cwd: Path) -> Path:
    """Write the valid reference profile used by identifier tests."""
    old_log = tmp_path / "old-rollout.jsonl"
    write_records(old_log, valid_records(thread_id="thread-old", cwd=cwd, sentinel="old sentinel"))
    return old_log


def candidate_path(isolated_env: IsolatedEnvironment, name: str = "candidate") -> Path:
    """Return a generated path in the isolated discovery tree."""
    path = isolated_env.home / ".codex" / "sessions" / "generated" / f"rollout-{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def run_identifier(
    isolated_env: IsolatedEnvironment,
    *arguments: str | Path,
) -> tuple[int, str, str]:
    """Run the identifier under the mandatory isolated environment."""
    result = isolated_env.run([PYTHON, "-I", IDENTIFIER, *arguments])
    return result.returncode, result.stdout, result.stderr


def test_argument_errors(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """Missing arguments and a naive SINCE value are usage errors."""
    code, stdout, _stderr = run_identifier(isolated_env)
    assert code == 2
    assert "Usage: codex-identify-thread.py" in stdout

    old_log = make_old_log(tmp_path, isolated_env.repo)
    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, "2039-01-01T00:00:00", old_log)
    assert code == 2
    assert "SINCE_ISO needs a time-zone offset" in stdout


def test_exactly_one_candidate_prints_summary(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """One matching generated rollout is selected and summarized."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    candidate = candidate_path(isolated_env)
    write_records(candidate, valid_records(thread_id="thread-candidate", cwd=isolated_env.repo))

    code, stdout, stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)

    assert code == 0, stderr
    assert "candidates: 1; unreadable look-alikes: 0" in stdout
    assert f"thread-candidate  2040-01-02T03:04:05Z  {candidate}" in stdout
    assert not (isolated_env.state / "active-codex-thread.json").exists()


@pytest.mark.parametrize("count", [0, 2])
def test_requires_exactly_one_candidate(isolated_env: IsolatedEnvironment, tmp_path: Path, count: int) -> None:
    """Zero or multiple matching rollouts are ambiguous."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    for number in range(count):
        write_records(
            candidate_path(isolated_env, str(number)),
            valid_records(thread_id=f"thread-{number}", cwd=isolated_env.repo),
        )

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log, "--write")

    assert code == 1
    assert f"candidates: {count}; unreadable look-alikes: 0" in stdout
    assert "exactly one readable candidate" in stdout
    assert not (isolated_env.state / "active-codex-thread.json").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", "generated-other-source"),
        ("originator", "generated-other-originator"),
        ("cwd", "generated-relative-cwd"),
        ("timestamp", "2039-01-01T00:00:00Z"),
        ("timestamp", "2038-12-31T23:59:59Z"),
    ],
    ids=["source", "originator", "cwd", "created-at-since", "created-before-since"],
)
def test_candidate_metadata_filters(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    """Nonmatching source, originator, cwd or creation time is ignored."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    candidate = valid_records(thread_id="thread-filtered", cwd=isolated_env.repo)
    cast("dict[str, object]", candidate[0]["payload"])[field] = value
    write_records(candidate_path(isolated_env), candidate)

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)

    assert code == 1
    assert "candidates: 0; unreadable look-alikes: 0" in stdout


def test_wrong_sentinel_is_filtered_but_trailing_newlines_are_ignored(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Composer identity is exact apart from trailing newlines."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    candidate = candidate_path(isolated_env)
    write_records(candidate, valid_records(thread_id="thread-candidate", cwd=isolated_env.repo, sentinel="wrong"))
    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)
    assert code == 1
    assert "candidates: 0" in stdout

    write_records(candidate, valid_records(thread_id="thread-candidate", cwd=isolated_env.repo, sentinel=SENTINEL))
    code, stdout, stderr = run_identifier(isolated_env, SENTINEL + "\n\n", SINCE, old_log)
    assert code == 0, stderr
    assert "candidates: 1" in stdout


def test_old_log_is_skipped_during_discovery(isolated_env: IsolatedEnvironment) -> None:
    """The reference rollout cannot identify itself as the new thread."""
    old_log = candidate_path(isolated_env, "old")
    write_records(old_log, valid_records(thread_id="thread-old", cwd=isolated_env.repo))

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)

    assert code == 1
    assert "candidates: 0" in stdout


@pytest.mark.parametrize("kind", ["malformed", "wrong-first"])
@pytest.mark.parametrize("newer", [False, True])
def test_unreadable_look_alikes_fail_only_when_newer(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    kind: str,
    newer: bool,
) -> None:
    """Old damaged noise is ignored, while a new look-alike is ambiguous."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    write_records(candidate_path(isolated_env, "valid"), valid_records(thread_id="thread-valid", cwd=isolated_env.repo))
    damaged = candidate_path(isolated_env, "damaged")
    damaged.write_text("{not JSON}\n" if kind == "malformed" else '{"type": "turn_context"}\n', encoding="utf-8")
    stamp = 2_208_988_800 if newer else 946_684_800
    os.utime(damaged, (stamp, stamp))

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)

    assert code == (1 if newer else 0)
    assert f"unreadable look-alikes: {1 if newer else 0}" in stdout
    assert ("UNREADABLE" in stdout) is newer


def test_refuses_unreadable_old_log(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """A candidate cannot be compared against a damaged reference."""
    old_log = tmp_path / "old-rollout.jsonl"
    old_log.write_text("{not JSON}\n", encoding="utf-8")
    write_records(candidate_path(isolated_env), valid_records(thread_id="thread-valid", cwd=isolated_env.repo))

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)

    assert code == 1
    assert "FAIL: old log:" in stdout
    assert "malformed JSON" in stdout


@pytest.mark.parametrize("side", ["candidate", "old"])
def test_refuses_missing_turn_context(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    side: str,
) -> None:
    """Both the candidate and reference must establish a profile."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    candidate = candidate_path(isolated_env)
    new_records = valid_records(thread_id="thread-valid", cwd=isolated_env.repo)
    if side == "candidate":
        new_records = [record for record in new_records if record["type"] != "turn_context"]
    else:
        old_records = valid_records(thread_id="thread-old", cwd=isolated_env.repo, sentinel="old sentinel")
        write_records(old_log, [record for record in old_records if record["type"] != "turn_context"])
    write_records(candidate, new_records)

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log, "--write")

    assert code == 1
    assert "FAIL: missing turn_context" in stdout
    assert not (isolated_env.state / "active-codex-thread.json").exists()


@pytest.mark.parametrize("stopping_key", STOPPING_KEYS)
def test_refuses_drift_on_each_stopping_key(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    stopping_key: str,
) -> None:
    """Every behavioural-profile difference stops identification."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    records = valid_records(thread_id="thread-valid", cwd=isolated_env.repo)
    cast("dict[str, object]", records[1]["payload"])[stopping_key] = "generated drift"
    write_records(candidate_path(isolated_env), records)

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log, "--write")

    assert code == 1
    assert f"DIFF {stopping_key}:" in stdout
    assert f"profile differs from the old thread: {stopping_key}" in stdout
    assert not (isolated_env.state / "active-codex-thread.json").exists()


@pytest.mark.parametrize("diagnostic_key", ["timezone", "multi_agent_version", "disabled_plugin_ids"])
def test_diagnostic_drift_is_printed_but_allowed(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    diagnostic_key: str,
) -> None:
    """Diagnostic differences are visible without becoming stopping keys."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    records = valid_records(thread_id="thread-valid", cwd=isolated_env.repo)
    cast("dict[str, object]", records[1]["payload"])[diagnostic_key] = "generated diagnostic drift"
    write_records(candidate_path(isolated_env), records)

    code, stdout, stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)

    assert code == 0, stderr
    assert f"diff (diagnostic) {diagnostic_key}:" in stdout


def test_relocates_only_equal_or_descendant_paths(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Cross-project comparison relocates path segments, not shared prefixes."""
    old_repo = tmp_path / "x" / "repo"
    prefix_peer = old_repo.with_name(old_repo.name + "-other")
    old_records = valid_records(thread_id="thread-old", cwd=old_repo, sentinel="old sentinel")
    old_context = cast("dict[str, object]", old_records[1]["payload"])
    old_context["workspace_roots"] = [str(old_repo), str(old_repo / "nested"), str(prefix_peer)]
    old_context["file_system_sandbox_policy"] = {"writable_roots": [str(old_repo / "write"), str(prefix_peer)]}
    old_log = tmp_path / "old-rollout.jsonl"
    write_records(old_log, old_records)

    new_records = valid_records(thread_id="thread-new", cwd=isolated_env.repo)
    new_context = cast("dict[str, object]", new_records[1]["payload"])
    new_context["workspace_roots"] = [
        str(isolated_env.repo),
        str(isolated_env.repo / "nested"),
        str(prefix_peer),
    ]
    new_context["file_system_sandbox_policy"] = {"writable_roots": [str(isolated_env.repo / "write"), str(prefix_peer)]}
    write_records(candidate_path(isolated_env), new_records)

    code, stdout, stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)

    assert code == 0, stderr
    assert f"profile compared relocated: {old_repo} -> {isolated_env.repo}" in stdout
    assert "same workspace_roots:" in stdout
    assert "same file_system_sandbox_policy:" in stdout


def test_write_records_only_stopping_profile_keys(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """--write records identity, provenance and only the behavioural baseline."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    candidate = candidate_path(isolated_env)
    write_records(candidate, valid_records(thread_id="thread-new", cwd=isolated_env.repo))

    code, stdout, stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log, "--write")

    assert code == 0, stderr
    active_path = isolated_env.state / "active-codex-thread.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    assert active["thread_id"] == "thread-new"
    assert active["log_path"] == str(candidate)
    assert active["source"] == "vscode"
    assert active["originator"] == "codex_vscode"
    assert active["cwd"] == str(isolated_env.repo)
    assert active["created"] == "2040-01-02T03:04:05Z"
    assert active["sentinel"] == SENTINEL
    assert active["replaces_thread_log"] == str(old_log)
    assert set(active["profile_baseline"]) == set(STOPPING_KEYS)
    assert "recorded_at" in active
    assert f"written: {active_path}" in stdout


def test_0164_effective_profile_matches_0162_and_records_sources(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """An initial-turn settings event completes the reduced 0.164 context."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    candidate = candidate_path(isolated_env)
    write_records(candidate, valid_records_0164(thread_id="thread-new", cwd=isolated_env.repo))

    code, stdout, stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log, "--write")

    assert code == 0, stderr
    active = json.loads((isolated_env.state / "active-codex-thread.json").read_text(encoding="utf-8"))
    assert active["profile_baseline"]["personality"] == "pragmatic"
    assert active["profile_baseline"]["workspace_roots"] == [str(isolated_env.repo)]
    assert 'same personality: "pragmatic" (source: thread_settings_applied)' in stdout
    assert f"same workspace_roots: [\"{isolated_env.repo}\"] (source: thread_settings_applied)" in stdout
    assert 'same model: "synthetic-model" (source: turn_context)' in stdout


def test_identifier_refuses_0164_without_initial_turn_settings(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Missing fallback values make the candidate profile unknown."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    records = valid_records_0164(thread_id="thread-new", cwd=isolated_env.repo)
    records = [
        record
        for record in records
        if cast("dict[str, object]", record.get("payload") or {}).get("type") != "thread_settings_applied"
    ]
    write_records(candidate_path(isolated_env), records)

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log, "--write")

    assert code == 1
    assert "unknown stopping keys: workspace_roots, personality" in stdout
    assert not (isolated_env.state / "active-codex-thread.json").exists()


def test_identifier_ignores_settings_outside_initial_turn(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """A later settings event cannot complete the initial profile."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    records = valid_records_0164(thread_id="thread-new", cwd=isolated_env.repo)
    settings = records.pop(-2)
    records.append(settings)
    write_records(candidate_path(isolated_env), records)

    code, stdout, _stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log, "--write")

    assert code == 1
    assert "unknown stopping keys: workspace_roots, personality" in stdout


def test_turn_context_value_wins_over_initial_turn_settings(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Settings events fill absent keys but never override context values."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    records = valid_records(thread_id="thread-new", cwd=isolated_env.repo)
    records.insert(-1, thread_settings_applied(cwd=isolated_env.repo, personality="different"))
    write_records(candidate_path(isolated_env), records)

    code, stdout, stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log)

    assert code == 0, stderr
    assert 'same personality: "pragmatic" (source: turn_context)' in stdout


def test_identifier_records_and_reports_cli_versions(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """A version change is visible but does not prevent a verified renewal."""
    old_log = make_old_log(tmp_path, isolated_env.repo)
    candidate = candidate_path(isolated_env)
    records = valid_records(thread_id="thread-new", cwd=isolated_env.repo)
    metadata = cast("dict[str, object]", records[0]["payload"])
    metadata["cli_version"] = "0.164.0-alpha.11.1"
    write_records(candidate, records)

    code, stdout, stderr = run_identifier(isolated_env, SENTINEL, SINCE, old_log, "--write")

    assert code == 0, stderr
    active = json.loads((isolated_env.state / "active-codex-thread.json").read_text(encoding="utf-8"))
    assert active.get("cli_version") == "0.164.0-alpha.11.1"
    assert f"old CLI version: {CLI_VERSION}" in stdout
    assert "new CLI version: 0.164.0-alpha.11.1" in stdout
