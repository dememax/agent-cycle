# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Generated-turn tests for the turn-record skeleton — agent-cycle project

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from .conftest import PYTHON, ROOT

if TYPE_CHECKING:
    from pathlib import Path

RECORD = ROOT / "bin" / "turn-record.py"
HEAD_A = "a" * 40
HEAD_B = "b" * 40
REFS_A = "1" * 16
REFS_B = "2" * 16
STATUS_A = "3" * 16
STATUS_B = "4" * 16


def snapshot_line(
    repository: str,
    *,
    head: str = HEAD_A,
    refs: str = REFS_A,
    codex_refs: int = 1,
    status: str = STATUS_A,
) -> str:
    """Build one generated snapshot record."""
    return f"{repository} head={head} refs={refs} codex_refs={codex_refs} status={status}\n"


def create_turn(
    tmp_path: Path,
    *,
    audit: str | None = None,
    before: str | None = None,
    after: str | None = None,
) -> Path:
    """Create a generated turn directory with every required input."""
    turn = tmp_path / "turn-101"
    turn.mkdir()
    (turn / "started").write_text("2026-01-02 03:04:05 +0000\n", encoding="utf-8")
    (turn / "finished").write_text("2026-01-02 03:05:06 +0000\n", encoding="utf-8")
    (turn / "audit.txt").write_text(
        audit or "approvals_reviewer: auto_review\nresult: valid\naudit exit 0\n",
        encoding="utf-8",
    )
    (turn / "snapshot-before.txt").write_text(
        before or snapshot_line("/generated/project"),
        encoding="utf-8",
    )
    (turn / "snapshot-after.txt").write_text(
        after or snapshot_line("/generated/project"),
        encoding="utf-8",
    )
    return turn


def run_record(turn: Path) -> subprocess.CompletedProcess[bytes]:
    """Run the generator without interpreting its byte streams."""
    return subprocess.run([PYTHON, RECORD, turn], capture_output=True, check=False)


def test_clean_implementation_turn(tmp_path: Path) -> None:
    audit = (
        "12:00:00 ESCALATION ok  [/generated/project] git add generated\n"
        "12:00:01 ESCALATION ok  [/generated/project] git commit -F /tmp/generated\n"
        "approvals_reviewer: auto_review\n"
        "result: valid\n"
        "audit exit 0\n"
    )
    turn = create_turn(
        tmp_path,
        audit=audit,
        after=snapshot_line("/generated/project", head=HEAD_B),
    )
    (turn / "turn-id").write_text("generated-turn-id\n", encoding="utf-8")
    (turn / "pre-state.txt").write_text("head generated\nstatus 0\n", encoding="utf-8")
    (turn / "result.json").write_text(
        json.dumps(
            {
                "status": "ready_for_review",
                "commits": [
                    {"role": "red", "sha": "abcdef012345", "subject": "generated RED"},
                    {"role": "green", "sha": "123456789abc", "subject": "generated GREEN"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (turn / "usage-row.txt").write_text(
        '| turn | values |\n|---|---|\n| turn-101 | 1 → 2 |\nrenewal: {"triggers":[]}\n',
        encoding="utf-8",
    )

    result = run_record(turn)

    assert result.returncode == 0, result.stderr
    assert result.stdout.decode() == (
        "- Turn turn-101: 2026-01-02 03:04:05 +0000 - 2026-01-02 03:05:06 +0000\n"
        "- Turn ID: generated-turn-id\n"
        "- Audit: 2 escalations (2 ok, 0 BAD); result valid; exit 0\n"
        f"- Snapshot /generated/project: head {HEAD_A} → {HEAD_B}\n"
        "- Result: status ready_for_review; commits red abcdef0: generated RED; green 1234567: generated GREEN\n"
        "- | turn-101 | 1 → 2 |\n"
        '- renewal: {"triggers":[]}\n'
        '- Pre-state: "head generated\\nstatus 0"\n'
    )
    assert result.stderr == b""


def test_review_turn_reports_findings(tmp_path: Path) -> None:
    turn = create_turn(tmp_path)
    (turn / "result.json").write_text(
        json.dumps(
            {
                "verdict": "changes_requested",
                "findings": [
                    {"id": "GENERATED/B1", "severity": "blocker"},
                    {"id": "GENERATED/n1", "severity": "note"},
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_record(turn)

    assert result.returncode == 0, result.stderr
    assert "- Snapshots: identical\n" in result.stdout.decode()
    assert (
        "- Result: verdict changes_requested; findings GENERATED/B1 (blocker); GENERATED/n1 (note)\n"
        in result.stdout.decode()
    )


def test_invalid_result_bad_escalation_and_turn_error(tmp_path: Path) -> None:
    turn = create_turn(
        tmp_path,
        audit=(
            "12:00:00 ESCALATION BAD [/generated/project] git push generated\n"
            "approvals_reviewer: auto_review\n"
            "TURN ERROR: usage_limit: generated exhaustion\n"
            "result: INVALID: duplicate key status\n"
            "audit exit 7\n"
        ),
    )

    result = run_record(turn)

    assert result.returncode == 0, result.stderr
    assert (
        "- Audit: 1 escalation (0 ok, 1 BAD); result INVALID: duplicate key status; "
        "TURN ERROR: usage_limit: generated exhaustion; exit 7\n"
    ) in result.stdout.decode()
    assert "- result.json: absent\n" in result.stdout.decode()


def test_snapshot_reports_only_changed_repositories_and_fields(tmp_path: Path) -> None:
    before = snapshot_line("/generated/project") + snapshot_line("/generated/other")
    after = snapshot_line("/generated/project", head=HEAD_B) + snapshot_line(
        "/generated/other",
        refs=REFS_B,
        codex_refs=2,
        status=STATUS_B,
    )
    turn = create_turn(tmp_path, before=before, after=after)

    result = run_record(turn)

    assert result.returncode == 0, result.stderr
    output = result.stdout.decode()
    assert f"- Snapshot /generated/project: head {HEAD_A} → {HEAD_B}\n" in output
    assert (
        f"- Snapshot /generated/other: refs {REFS_A} → {REFS_B}; codex_refs 1 → 2; status {STATUS_A} → {STATUS_B}\n"
    ) in output


def test_missing_optional_files_are_reported(tmp_path: Path) -> None:
    turn = create_turn(
        tmp_path,
        audit="approvals_reviewer: auto_review\nresult: valid\n",
    )

    result = run_record(turn)

    assert result.returncode == 0, result.stderr
    output = result.stdout.decode()
    assert "- Turn ID: absent\n" in output
    assert "- Audit: 0 escalations (0 ok, 0 BAD); result valid; exit status not recorded\n" in output
    assert "- result.json: absent\n" in output
    assert "- usage-row.txt: absent\n" in output
    assert "- pre-state.txt: absent\n" in output


@pytest.mark.parametrize(
    "filename",
    ["started", "finished", "audit.txt", "snapshot-before.txt", "snapshot-after.txt"],
)
def test_missing_required_file_fails_closed(tmp_path: Path, filename: str) -> None:
    turn = create_turn(tmp_path)
    (turn / filename).unlink()

    result = run_record(turn)

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == f"turn-record: {turn / filename}: missing required file\n".encode()


def test_unreadable_required_file_fails_closed(tmp_path: Path) -> None:
    turn = create_turn(tmp_path)
    path = turn / "started"
    path.chmod(0)

    result = run_record(turn)

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == f"turn-record: {path}: cannot read\n".encode()


def test_unparseable_audit_fails_closed(tmp_path: Path) -> None:
    turn = create_turn(tmp_path, audit="generated text that is not audit output\n")

    result = run_record(turn)

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == f"turn-record: {turn / 'audit.txt'}: cannot parse\n".encode()


@pytest.mark.parametrize("filename", ["snapshot-before.txt", "snapshot-after.txt"])
def test_unparseable_snapshot_fails_closed(tmp_path: Path, filename: str) -> None:
    turn = create_turn(tmp_path)
    (turn / filename).write_text("incomplete generated snapshot\n", encoding="utf-8")

    result = run_record(turn)

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == f"turn-record: {turn / filename}: cannot parse\n".encode()
