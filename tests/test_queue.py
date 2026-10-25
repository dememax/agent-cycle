# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box characterization of the fail-closed queue wrapper — agent-cycle project

from __future__ import annotations

import fcntl
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest

from .conftest import ROOT, IsolatedEnvironment
from .rollout import composer, session_meta, task_complete, task_started, turn_context, write_records

if TYPE_CHECKING:
    from pathlib import Path

QUEUE = ROOT / "bin" / "codex-queue-turn.sh"
SENTINEL = "generated orientation sentinel"
PROMPT = "[S0 DRIVER: Claude Code]\nGenerated test turn.\n"
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
TURN_FILES = ("thread-log-path", "thread-log-lines-before", "started", "stdout.txt", "stderr.txt", "turn-id")


@dataclass
class QueueCase:
    """One valid generated active thread, ready for a queue invocation."""

    state: Path
    log: Path
    turn_dir: Path
    records: list[dict[str, object]]
    active: dict[str, object]

    def write_log(self) -> None:
        """Rewrite the generated rollout after a test mutation."""
        write_records(self.log, self.records)

    def write_active(self) -> None:
        """Rewrite the generated active-thread record after a test mutation."""
        (self.state / "active-codex-thread.json").write_text(
            json.dumps(self.active) + "\n",
            encoding="utf-8",
        )


def make_case(isolated_env: IsolatedEnvironment, tmp_path: Path, *, state: Path | None = None) -> QueueCase:
    """Create the minimum valid pre-submission state."""
    selected_state = state or isolated_env.state
    selected_state.mkdir(parents=True, exist_ok=True)
    log = tmp_path / f"rollout-{selected_state.name}.jsonl"
    context = turn_context(cwd=isolated_env.repo)
    baseline = dict(cast("dict[str, object]", context["payload"]))
    records = [
        session_meta(thread_id="thread-generated", cwd=isolated_env.repo),
        context,
        task_started("turn-initial"),
        composer("turn-initial", SENTINEL),
        task_complete("turn-initial"),
    ]
    turn_dir = tmp_path / f"turn-{selected_state.name}"
    turn_dir.mkdir()
    (turn_dir / "prompt.md").write_text(PROMPT, encoding="utf-8")
    active: dict[str, object] = {
        "thread_id": "thread-generated",
        "log_path": str(log),
        "source": "vscode",
        "originator": "codex_vscode",
        "cwd": str(isolated_env.repo),
        "created": "2040-01-02T03:04:05Z",
        "sentinel": SENTINEL,
        "profile_baseline": baseline,
    }
    case = QueueCase(selected_state, log, turn_dir, records, active)
    case.write_log()
    case.write_active()
    return case


def run_queue(
    isolated_env: IsolatedEnvironment,
    case: QueueCase,
    mode: str = "none",
    *,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run the shell entry point with a selected deterministic fake outcome."""
    fake_environment = {
        "FAKE_CODEX_MODE": mode,
        "FAKE_CODEX_LOG": str(case.log),
        "FAKE_CODEX_PROMPT": str(case.turn_dir / "prompt.md"),
    }
    fake_environment.update(extra_env or {})
    result = isolated_env.run([QUEUE, case.turn_dir], extra_env=fake_environment)
    return result.returncode, result.stdout, result.stderr


def assert_pre_submission_refusal(case: QueueCase, result: tuple[int, str, str], message: str) -> None:
    """Assert a refusal before the durable submission marker is created."""
    returncode, _stdout, stderr = result
    assert returncode == 1
    assert "codex-queue-turn: REFUSED:" in stderr
    assert message in stderr
    assert not (case.state / "pending.json").exists()
    assert all(not (case.turn_dir / name).exists() for name in TURN_FILES)


def test_refuses_without_active_record(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """No active record means no state or turn files are created."""
    turn_dir = tmp_path / "turn"
    turn_dir.mkdir()
    case = QueueCase(isolated_env.state, tmp_path / "unused.jsonl", turn_dir, [], {})

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "no active-codex-thread.json")


def test_refuses_without_codex_binary(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """An explicit missing CLI is not replaced by discovery under HOME."""
    case = make_case(isolated_env, tmp_path)

    result = run_queue(isolated_env, case, extra_env={"CODEX": str(tmp_path / "missing-codex")})

    assert_pre_submission_refusal(case, result, "codex binary not found")


def test_refuses_when_queue_lock_is_held(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """A concurrent driver owns the state directory's exclusive lock."""
    case = make_case(isolated_env, tmp_path)
    with (case.state / "queue.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_queue(isolated_env, case)

    assert_pre_submission_refusal(case, result, "queue.lock held")


def test_refuses_an_existing_pending_marker(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """A previous ambiguous submission must be investigated by a person."""
    case = make_case(isolated_env, tmp_path)
    pending = '{"generated": true}\n'
    (case.state / "pending.json").write_text(pending, encoding="utf-8")

    returncode, _stdout, stderr = run_queue(isolated_env, case)

    assert returncode == 1
    assert "earlier submission never started a turn" in stderr
    assert (case.state / "pending.json").read_text(encoding="utf-8") == pending
    assert all(not (case.turn_dir / name).exists() for name in TURN_FILES)


def test_refuses_record_for_another_repository(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """The active record cannot redirect the selected repository."""
    case = make_case(isolated_env, tmp_path)
    case.active["cwd"] = str(tmp_path / "another-project")
    case.write_active()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "is not the selected repository")


def test_refuses_a_missing_record_key(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """A partial active record does not inherit data from the log."""
    case = make_case(isolated_env, tmp_path)
    del case.active["thread_id"]
    case.write_active()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "active record lacks thread_id")


@pytest.mark.parametrize(
    ("active_key", "meta_field"),
    [
        ("thread_id", "id"),
        ("source", "source"),
        ("originator", "originator"),
        ("cwd", "cwd"),
        ("created", "timestamp"),
    ],
)
def test_refuses_each_session_meta_mismatch(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    active_key: str,
    meta_field: str,
) -> None:
    """Every recorded session identity field must equal the rollout metadata."""
    case = make_case(isolated_env, tmp_path)
    metadata = cast("dict[str, object]", case.records[0]["payload"])
    metadata[meta_field] = "different-generated-value"
    case.write_log()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), f"session_meta {meta_field}")
    assert case.active[active_key] != metadata[meta_field]


def test_refuses_wrong_sentinel(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """The record cannot name a different initial composer message."""
    case = make_case(isolated_env, tmp_path)
    case.active["sentinel"] = "different generated sentinel"
    case.write_active()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "not the recorded sentinel")


def test_refuses_a_running_turn(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """A new prompt is not queued while any prior turn remains running."""
    case = make_case(isolated_env, tmp_path)
    case.records.append(task_started("turn-running"))
    case.write_log()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "turn running: ['turn-running']")


def test_refuses_without_turn_context(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """The wrapper cannot infer a behavioural profile without a context."""
    case = make_case(isolated_env, tmp_path)
    case.records = [record for record in case.records if record["type"] != "turn_context"]
    case.write_log()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "no turn_context")


@pytest.mark.parametrize("stopping_key", STOPPING_KEYS)
def test_refuses_drift_on_each_stopping_key(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    stopping_key: str,
) -> None:
    """Any one changed profile key stops queueing."""
    case = make_case(isolated_env, tmp_path)
    context = cast("dict[str, object]", case.records[1]["payload"])
    context[stopping_key] = "drifted-generated-value"
    case.write_log()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), f"profile drift on: {stopping_key}")


def test_refuses_an_unreadable_log(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """A disappeared log is a closed failure, not an empty baseline."""
    case = make_case(isolated_env, tmp_path)
    case.log.unlink()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "log check failed:")


def test_refuses_without_prompt_file(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """There is no implicit or empty prompt."""
    case = make_case(isolated_env, tmp_path)
    (case.turn_dir / "prompt.md").unlink()

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "no prompt.md")


def test_refuses_prompt_without_driver_header(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """Only the driver's explicitly marked prompt may be submitted."""
    case = make_case(isolated_env, tmp_path)
    (case.turn_dir / "prompt.md").write_text("Generated but unmarked prompt.\n", encoding="utf-8")

    assert_pre_submission_refusal(case, run_queue(isolated_env, case), "lacks the driver header")


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("hang", "did not return"),
        ("nonzero", "codex queue failed (exit 23)"),
        ("malformed", "log unreadable after submission"),
        ("two", "more than one new turn appeared"),
        ("foreign", "does not carry the submitted prompt"),
        ("none", "submitted turn was not observed"),
    ],
)
def test_post_submission_failure_keeps_marker_and_blocks_later_calls(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    mode: str,
    message: str,
) -> None:
    """Every ambiguous submission outcome persists and stops the next call."""
    case = make_case(isolated_env, tmp_path)

    returncode, _stdout, stderr = run_queue(isolated_env, case, mode)

    assert returncode == 1
    assert message in stderr
    pending = case.state / "pending.json"
    assert pending.is_file()
    pending_contents = pending.read_text(encoding="utf-8")
    assert (case.turn_dir / "thread-log-path").is_file()
    assert (case.turn_dir / "thread-log-lines-before").is_file()
    assert (case.turn_dir / "started").is_file()
    if mode == "hang":
        assert not (case.turn_dir / "stdout.txt").exists()
        assert not (case.turn_dir / "stderr.txt").exists()
    else:
        assert (case.turn_dir / "stdout.txt").is_file()
        assert (case.turn_dir / "stderr.txt").is_file()
    later_code, _later_stdout, later_stderr = run_queue(isolated_env, case)
    assert later_code == 1
    assert "earlier submission never started a turn" in later_stderr
    assert pending.read_text(encoding="utf-8") == pending_contents
    assert not (case.turn_dir / "turn-id").exists()


@pytest.mark.parametrize("mode", ["partial_then_turn", "started_then_composer"])
def test_waiting_state_can_resolve_to_success(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    mode: str,
) -> None:
    """An incomplete line or temporarily missing composer is polled again."""
    case = make_case(isolated_env, tmp_path)

    returncode, stdout, stderr = run_queue(
        isolated_env,
        case,
        mode,
        extra_env={"S0_QUEUE_TIMEOUT": "7", "FAKE_CODEX_STAGE_DELAY": "3.4"},
    )

    assert returncode == 0, stderr
    assert "turn-delayed" in stdout
    assert (case.turn_dir / "turn-id").read_text(encoding="utf-8") == "turn-delayed\n"
    assert not (case.state / "pending.json").exists()


@pytest.mark.parametrize("mode", ["partial_forever", "started_only"])
def test_waiting_state_times_out_and_keeps_pending(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    mode: str,
) -> None:
    """An unresolved incomplete line or absent composer remains ambiguous."""
    case = make_case(isolated_env, tmp_path)

    returncode, _stdout, stderr = run_queue(
        isolated_env,
        case,
        mode,
        extra_env={"S0_QUEUE_TIMEOUT": "3.2"},
    )

    assert returncode == 1
    assert "submitted turn was not observed" in stderr
    assert (case.state / "pending.json").is_file()
    assert not (case.turn_dir / "turn-id").exists()


def test_two_composer_messages_for_new_turn_refuse(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """Even two identical composer messages make the new turn ambiguous."""
    case = make_case(isolated_env, tmp_path)

    returncode, _stdout, stderr = run_queue(isolated_env, case, "duplicate_composer")

    assert returncode == 1
    assert "does not carry the submitted prompt" in stderr
    assert (case.state / "pending.json").is_file()
    assert not (case.turn_dir / "turn-id").exists()


def test_success_records_turn_and_removes_pending_marker(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """The normal path records all evidence and durably resolves pending state."""
    case = make_case(isolated_env, tmp_path)
    lines_before = len(case.records)

    returncode, stdout, stderr = run_queue(isolated_env, case, "turn")

    assert returncode == 0, stderr
    assert "queued; turn turn-new started with the submitted prompt" in stdout
    assert (case.turn_dir / "thread-log-path").read_text(encoding="utf-8") == f"{case.log}\n"
    assert (case.turn_dir / "thread-log-lines-before").read_text(encoding="utf-8") == f"{lines_before}\n"
    assert (case.turn_dir / "started").read_text(encoding="utf-8").endswith("\n")
    assert (case.turn_dir / "stdout.txt").read_text(encoding="utf-8") == (
        "queued by fake codex\nqueue_exit=0 thread=thread-generated\n"
    )
    assert (case.turn_dir / "stderr.txt").read_text(encoding="utf-8") == ""
    assert (case.turn_dir / "turn-id").read_text(encoding="utf-8") == "turn-new\n"
    assert not (case.state / "pending.json").exists()


def test_prompt_rewritten_after_submission_still_matches_original(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Validation, submission and comparison all use the one locked read."""
    case = make_case(isolated_env, tmp_path)

    returncode, stdout, stderr = run_queue(isolated_env, case, "rewrite")

    assert returncode == 0, stderr
    assert "turn-rewrite" in stdout
    assert (case.turn_dir / "prompt.md").read_text(encoding="utf-8") == "rewritten after submission\n"
    assert (case.turn_dir / "turn-id").read_text(encoding="utf-8") == "turn-rewrite\n"
    assert not (case.state / "pending.json").exists()


def test_legacy_state_variable_overrides_selected_state(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """S0_STATE_DIR selects all queue state when it is present."""
    override = tmp_path / "legacy-state"
    case = make_case(isolated_env, tmp_path, state=override)

    returncode, _stdout, stderr = run_queue(
        isolated_env,
        case,
        "turn",
        extra_env={"S0_STATE_DIR": str(override)},
    )

    assert returncode == 0, stderr
    assert (override / "queue.lock").is_file()
    assert not (isolated_env.state / "queue.lock").exists()
    assert (case.turn_dir / "turn-id").read_text(encoding="utf-8") == "turn-new\n"
