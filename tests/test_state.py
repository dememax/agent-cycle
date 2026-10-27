# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Generated-state tests for the restart summary — agent-cycle project

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .conftest import PYTHON, ROOT, IsolatedEnvironment
from .rollout import record, session_meta, task_complete, task_started, token_count, write_records

if TYPE_CHECKING:
    import subprocess
    from pathlib import Path

STATE = ROOT / "bin" / "state.py"


@dataclass
class StateCase:
    """One wholly generated repository, active record, log and turn."""

    log: Path
    active: Path
    turn: Path
    records: list[dict[str, object]]

    def write_log(self) -> None:
        """Write the current synthetic rollout records."""
        write_records(self.log, self.records)


def git(isolated_env: IsolatedEnvironment, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run Git only in the generated repository."""
    return isolated_env.run(["git", "-C", isolated_env.repo, *arguments])


def commit(isolated_env: IsolatedEnvironment, message: str) -> str:
    """Commit generated content with an isolated test identity."""
    result = git(
        isolated_env,
        "-c",
        "user.name=Generated Test",
        "-c",
        "user.email=generated",
        "commit",
        "-q",
        "-am",
        message,
    )
    assert result.returncode == 0, result.stderr
    head = git(isolated_env, "rev-parse", "HEAD")
    assert head.returncode == 0, head.stderr
    return head.stdout.strip()


def rate_record(primary: float, secondary: float, primary_reset: int, secondary_reset: int) -> dict[str, object]:
    """Build a complete generated Codex rate-limit record."""
    item = token_count(
        total={"input_tokens": 10},
        last={"input_tokens": 10},
        primary_used=primary,
        secondary_used=secondary,
    )
    payload = cast("dict[str, Any]", item["payload"])
    limits = cast("dict[str, Any]", payload["rate_limits"])
    cast("dict[str, Any]", limits["primary"])["resets_at"] = primary_reset
    cast("dict[str, Any]", limits["secondary"])["resets_at"] = secondary_reset
    return item


def make_case(isolated_env: IsolatedEnvironment, tmp_path: Path, *, notes: bool = True) -> StateCase:
    """Create a quiet state whose facts all come from generated inputs."""
    initialized = git(isolated_env, "init", "-q", "-b", "main")
    assert initialized.returncode == 0, initialized.stderr
    tracked = isolated_env.repo / "tracked.txt"
    tracked.write_text("generated one\n", encoding="utf-8")
    added = git(isolated_env, "add", "tracked.txt")
    assert added.returncode == 0, added.stderr
    head = commit(isolated_env, "generated initial")
    origin = git(isolated_env, "update-ref", "refs/remotes/origin/main", head)
    assert origin.returncode == 0, origin.stderr

    log = tmp_path / "rollout-generated.jsonl"
    records = [
        session_meta(thread_id="thread-generated", cwd=isolated_env.repo),
        task_started("turn-one"),
        rate_record(11, 22, 2_208_988_800, 2_209_593_600),
        task_complete("turn-one"),
        record("compacted", {}),
        rate_record(31, 42, 2_208_988_900, 2_209_593_700),
    ]
    write_records(log, records)
    active = isolated_env.state / "active-codex-thread.json"
    active.write_text(
        json.dumps(
            {
                "thread_id": "thread-generated",
                "log_path": str(log),
                "sentinel": "generated sentinel",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    turn = isolated_env.state / "turn-007"
    turn.mkdir()
    (turn / "finished").write_text("2040-01-02 04:05:06 +0100\n", encoding="utf-8")
    (turn / "audit.txt").write_text("generated audit output\naudit exit 0\n", encoding="utf-8")
    if notes:
        (isolated_env.state / "notes.md").write_text(
            "Next: generated action.\n\nDecision: generated choice.\n",
            encoding="utf-8",
        )
    return StateCase(log, active, turn, records)


def run_state(
    isolated_env: IsolatedEnvironment,
    *arguments: str,
) -> subprocess.CompletedProcess[str]:
    """Run the state tool in isolated mode against generated state."""
    return isolated_env.run([PYTHON, "-I", STATE, *arguments])


def fact(payload: dict[str, Any], section: str, name: str) -> dict[str, Any]:
    """Return one fact from the generated JSON cache."""
    return cast("dict[str, Any]", payload[section][name])


def assert_source(item: dict[str, Any]) -> None:
    """Every fact identifies a path plus a timestamp or content fingerprint."""
    source = item["source"]
    assert source["path"]
    assert {"modified_at", "parent_modified_at", "sha256"} & source.keys()


def test_quiet_state_reports_all_available_facts(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    case = make_case(isolated_env, tmp_path)

    result = run_state(isolated_env)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "# Generated agent-cycle state" in result.stdout
    assert "Next: generated action.\n\nDecision: generated choice.\n" in result.stdout
    assert not (isolated_env.state / "STATE.json").exists()
    assert not (isolated_env.state / "STATE.md").exists()

    written = run_state(isolated_env, "--write")
    assert written.returncode == 0, written.stderr
    assert written.stdout == result.stdout
    payload = json.loads((isolated_env.state / "STATE.json").read_text(encoding="utf-8"))
    assert fact(payload, "repository", "head")["value"] == git(isolated_env, "rev-parse", "HEAD").stdout.strip()
    assert fact(payload, "repository", "branch")["value"] == "main"
    assert fact(payload, "repository", "origin_ref")["value"] == fact(payload, "repository", "head")["value"]
    assert fact(payload, "repository", "dirty_entries")["value"] == 0
    assert fact(payload, "repository", "ahead_of_origin")["value"] == 0
    assert fact(payload, "active_thread", "thread_id")["value"] == "thread-generated"
    assert fact(payload, "active_thread", "log_path")["value"] == str(case.log)
    assert fact(payload, "active_thread", "sentinel")["value"] == "generated sentinel"
    assert fact(payload, "thread", "turns")["value"] == 1
    assert fact(payload, "thread", "running")["value"] is False
    assert fact(payload, "thread", "compacted_records")["value"] == 1
    assert fact(payload, "submission", "pending")["value"] is False
    assert fact(payload, "rate_limits", "five_hour_used_percent")["value"] == 31
    assert fact(payload, "rate_limits", "weekly_used_percent")["value"] == 42
    assert "+" in fact(payload, "rate_limits", "five_hour_resets_at")["value"]
    assert "+" in fact(payload, "rate_limits", "weekly_resets_at")["value"]
    assert fact(payload, "newest_turn", "name")["value"] == "turn-007"
    assert fact(payload, "newest_turn", "finished")["value"] == "2040-01-02 04:05:06 +0100"
    assert fact(payload, "newest_turn", "audit_exit")["value"] == "audit exit 0"
    assert fact(payload, "notes", "content")["value"] == ("Next: generated action.\n\nDecision: generated choice.\n")
    for section in payload.values():
        if not isinstance(section, dict):
            continue
        for item in section.values():
            if isinstance(item, dict) and "value" in item:
                assert_source(item)


def test_running_turn_is_reported(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    case = make_case(isolated_env, tmp_path)
    case.records.append(task_started("turn-running"))
    case.write_log()

    result = run_state(isolated_env, "--write")

    assert result.returncode == 0, result.stderr
    payload = json.loads((isolated_env.state / "STATE.json").read_text(encoding="utf-8"))
    assert fact(payload, "thread", "turns")["value"] == 2
    assert fact(payload, "thread", "running")["value"] is True


def test_pending_marker_is_reported(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    make_case(isolated_env, tmp_path)
    (isolated_env.state / "pending.json").write_text('{"generated": true}\n', encoding="utf-8")

    result = run_state(isolated_env, "--write")

    assert result.returncode == 0, result.stderr
    payload = json.loads((isolated_env.state / "STATE.json").read_text(encoding="utf-8"))
    assert fact(payload, "submission", "pending")["value"] is True


def test_missing_notes_are_explicit(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    make_case(isolated_env, tmp_path, notes=False)

    result = run_state(isolated_env, "--write")

    assert result.returncode == 0, result.stderr
    assert "## Driver notes\n\nabsent\n" in result.stdout
    payload = json.loads((isolated_env.state / "STATE.json").read_text(encoding="utf-8"))
    notes = fact(payload, "notes", "content")
    assert notes["value"] == "absent"
    assert "parent_modified_at" in notes["source"]


def test_unreadable_log_makes_all_log_facts_unknown(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    case = make_case(isolated_env, tmp_path)
    case.log.unlink()
    case.log.mkdir()

    result = run_state(isolated_env, "--write")

    assert result.returncode == 0, result.stderr
    payload = json.loads((isolated_env.state / "STATE.json").read_text(encoding="utf-8"))
    for section, name in (
        ("thread", "turns"),
        ("thread", "running"),
        ("thread", "compacted_records"),
        ("rate_limits", "five_hour_used_percent"),
        ("rate_limits", "weekly_used_percent"),
        ("rate_limits", "five_hour_resets_at"),
        ("rate_limits", "weekly_resets_at"),
    ):
        item = fact(payload, section, name)
        assert item["value"] is None
        assert "unknown" in item
        assert "cannot read" in item["unknown"]


def test_ahead_of_origin_commits_are_counted(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    make_case(isolated_env, tmp_path)
    (isolated_env.repo / "tracked.txt").write_text("generated two\n", encoding="utf-8")
    commit(isolated_env, "generated ahead")

    result = run_state(isolated_env, "--write")

    assert result.returncode == 0, result.stderr
    payload = json.loads((isolated_env.state / "STATE.json").read_text(encoding="utf-8"))
    assert fact(payload, "repository", "ahead_of_origin")["value"] == 1


def test_write_publishes_both_caches_atomically(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    make_case(isolated_env, tmp_path)

    result = run_state(isolated_env, "--write")

    assert result.returncode == 0, result.stderr
    json_path = isolated_env.state / "STATE.json"
    markdown_path = isolated_env.state / "STATE.md"
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert markdown_path.read_text(encoding="utf-8") == result.stdout
    assert not list(isolated_env.state.glob(".STATE.*.tmp"))


def test_profile_error_is_one_configuration_line(
    isolated_env: IsolatedEnvironment,
) -> None:
    isolated_env.profile.write_text("profile_version = [\n", encoding="utf-8")

    result = run_state(isolated_env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.count("\n") == 1
    assert result.stderr.startswith("state: configuration error:")
    assert "invalid TOML" in result.stderr


def test_unparseable_active_record_is_a_configuration_error(
    isolated_env: IsolatedEnvironment,
) -> None:
    active = isolated_env.state / "active-codex-thread.json"
    active.write_text('{"thread_id": 3}\n', encoding="utf-8")

    result = run_state(isolated_env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.count("\n") == 1
    assert result.stderr.startswith("state: active-codex-thread.json:")
    assert "unparseable" in result.stderr
