#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Factual Markdown skeleton for one completed turn — agent-cycle project
"""Print the factual part of a turn record from its evidence directory.

Usage: turn-record.py TURN_DIR
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SNAPSHOT_LINE = re.compile(
    r"^(?P<path>.+) head=(?P<head>[0-9a-f]{40}|none) refs=(?P<refs>[0-9a-f]{16}) "
    r"codex_refs=(?P<codex_refs>[0-9]+) status=(?P<status>[0-9a-f]{16})$"
)
ESCALATION_LINE = re.compile(r"^(?:[0-9]{2}:[0-9]{2}:[0-9]{2}|) ESCALATION (?P<result>ok |BAD) \[.*\] .*$")
SNAPSHOT_FIELDS = ("head", "refs", "codex_refs", "status")


class InputError(Exception):
    """A named turn input is unavailable or malformed."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason


@dataclass(frozen=True)
class Audit:
    """Facts parsed from an audit transcript."""

    ok: int
    bad: int
    result: str
    turn_error: str | None
    exit_status: int | None


def read_required(turn: Path, name: str) -> str:
    """Read one required UTF-8 file or identify why it is unavailable."""
    path = turn / name
    if not path.exists():
        raise InputError(path, "missing required file")
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        raise InputError(path, "cannot read") from None


def read_optional(turn: Path, name: str) -> str | None:
    """Read one optional UTF-8 file, distinguishing absence from failure."""
    path = turn / name
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        raise InputError(path, "cannot read") from None


def one_line(path: Path, content: str) -> str:
    """Require one non-empty logical line."""
    lines = content.splitlines()
    if len(lines) != 1 or not lines[0]:
        raise InputError(path, "cannot parse")
    return lines[0]


def parse_audit(path: Path, content: str) -> Audit:
    """Parse the stable stdout grammar of audit-turn.py plus its saved exit."""
    lines = content.splitlines()
    index = 0
    ok = 0
    bad = 0
    while index < len(lines):
        match = ESCALATION_LINE.fullmatch(lines[index])
        if match is None:
            break
        if match.group("result") == "ok ":
            ok += 1
        else:
            bad += 1
        index += 1

    if index >= len(lines) or not lines[index].startswith("approvals_reviewer:"):
        raise InputError(path, "cannot parse")
    index += 1

    turn_error = None
    if index < len(lines) and lines[index].startswith("TURN ERROR: "):
        turn_error = lines[index]
        index += 1

    if index >= len(lines) or not (lines[index] == "result: valid" or lines[index].startswith("result: INVALID: ")):
        raise InputError(path, "cannot parse")
    result = lines[index].removeprefix("result: ")
    index += 1

    exit_status = None
    if index < len(lines):
        match = re.fullmatch(r"audit exit ([0-9]+)", lines[index])
        if match is None:
            raise InputError(path, "cannot parse")
        exit_status = int(match.group(1))
        index += 1
    if index != len(lines):
        raise InputError(path, "cannot parse")
    return Audit(ok, bad, result, turn_error, exit_status)


def parse_snapshot(path: Path, content: str) -> dict[str, dict[str, str]]:
    """Parse complete repository snapshot lines, rejecting duplicates."""
    records: dict[str, dict[str, str]] = {}
    lines = content.splitlines()
    if not lines:
        raise InputError(path, "cannot parse")
    for line in lines:
        match = SNAPSHOT_LINE.fullmatch(line)
        if match is None:
            raise InputError(path, "cannot parse")
        values = match.groupdict()
        repository = values.pop("path")
        if repository in records:
            raise InputError(path, "cannot parse")
        records[repository] = values
    return records


def display(value: str) -> str:
    """Keep generated Markdown facts on one physical line."""
    return value.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


def snapshot_bullets(
    before: dict[str, dict[str, str]],
    after: dict[str, dict[str, str]],
) -> list[str]:
    """Describe only repositories and fields whose snapshot facts changed."""
    if before == after:
        return ["- Snapshots: identical"]
    bullets = []
    repositories = [*before, *(repository for repository in after if repository not in before)]
    for repository in repositories:
        old = before.get(repository)
        new = after.get(repository)
        if old == new:
            continue
        if old is None:
            changes = "repository absent → present"
        elif new is None:
            changes = "repository present → absent"
        else:
            changed = [f"{field} {old[field]} → {new[field]}" for field in SNAPSHOT_FIELDS if old[field] != new[field]]
            changes = "; ".join(changed)
        bullets.append(f"- Snapshot {display(repository)}: {changes}")
    return bullets


def string_field(value: object) -> str | None:
    """Return a string field without accepting another JSON type."""
    return value if isinstance(value, str) else None


def parse_result(path: Path, content: str) -> str:
    """Extract the schema-independent facts shared by result objects."""
    try:
        value: Any = json.loads(content)
    except ValueError:
        raise InputError(path, "cannot parse") from None
    if not isinstance(value, dict):
        raise InputError(path, "cannot parse")

    status = string_field(value.get("status"))
    verdict = string_field(value.get("verdict"))
    if (status is None) == (verdict is None):
        raise InputError(path, "cannot parse")
    facts = [f"status {display(status)}" if status is not None else f"verdict {display(verdict or '')}"]

    if "commits" in value:
        commits = value["commits"]
        if not isinstance(commits, list):
            raise InputError(path, "cannot parse")
        rendered = []
        for commit in commits:
            if not isinstance(commit, dict):
                raise InputError(path, "cannot parse")
            role = string_field(commit.get("role"))
            sha = string_field(commit.get("sha"))
            subject = string_field(commit.get("subject"))
            if role is None or not sha or subject is None:
                raise InputError(path, "cannot parse")
            rendered.append(f"{display(role)} {display(sha[:7])}: {display(subject)}")
        facts.append("commits " + ("; ".join(rendered) if rendered else "none"))

    if "findings" in value:
        findings = value["findings"]
        if not isinstance(findings, list):
            raise InputError(path, "cannot parse")
        rendered = []
        for finding in findings:
            if not isinstance(finding, dict):
                raise InputError(path, "cannot parse")
            identifier = string_field(finding.get("id"))
            severity = string_field(finding.get("severity"))
            if identifier is None or severity is None:
                raise InputError(path, "cannot parse")
            rendered.append(f"{display(identifier)} ({display(severity)})")
        facts.append("findings " + ("; ".join(rendered) if rendered else "none"))
    return "- Result: " + "; ".join(facts)


def parse_usage(path: Path, content: str) -> list[str]:
    """Select the data row and renewal facts from saved usage output."""
    rows = []
    renewal = []
    for line in content.splitlines():
        if line.startswith("renewal: "):
            renewal.append(line)
        elif line.startswith("| turn |") or re.fullmatch(r"\|(?:---\|)+", line):
            continue
        elif line.startswith("|") and line.endswith("|"):
            rows.append(line)
        else:
            raise InputError(path, "cannot parse")
    if len(rows) != 1 or len(renewal) != 1:
        raise InputError(path, "cannot parse")
    return [f"- {rows[0]}", f"- {renewal[0]}"]


def main(arguments: list[str]) -> int:
    """Parse all evidence before emitting a factual Markdown skeleton."""
    if len(arguments) != 1:
        print("turn-record: usage: turn-record.py TURN_DIR", file=sys.stderr)
        return 2
    turn = Path(arguments[0])
    try:
        started = one_line(turn / "started", read_required(turn, "started"))
        finished = one_line(turn / "finished", read_required(turn, "finished"))
        audit = parse_audit(turn / "audit.txt", read_required(turn, "audit.txt"))
        before = parse_snapshot(
            turn / "snapshot-before.txt",
            read_required(turn, "snapshot-before.txt"),
        )
        after = parse_snapshot(
            turn / "snapshot-after.txt",
            read_required(turn, "snapshot-after.txt"),
        )
        turn_id = read_optional(turn, "turn-id")
        result = read_optional(turn, "result.json")
        usage = read_optional(turn, "usage-row.txt")
        pre_state = read_optional(turn, "pre-state.txt")

        bullets = [f"- Turn {display(turn.name)}: {display(started)} - {display(finished)}"]
        bullets.append(
            "- Turn ID: absent" if turn_id is None else f"- Turn ID: {display(one_line(turn / 'turn-id', turn_id))}"
        )
        total = audit.ok + audit.bad
        noun = "escalation" if total == 1 else "escalations"
        audit_facts = f"- Audit: {total} {noun} ({audit.ok} ok, {audit.bad} BAD); result {audit.result}"
        if audit.turn_error is not None:
            audit_facts += f"; {audit.turn_error}"
        audit_facts += "; exit status not recorded" if audit.exit_status is None else f"; exit {audit.exit_status}"
        bullets.append(audit_facts)
        bullets.extend(snapshot_bullets(before, after))
        bullets.append("- result.json: absent" if result is None else parse_result(turn / "result.json", result))
        bullets.extend(["- usage-row.txt: absent"] if usage is None else parse_usage(turn / "usage-row.txt", usage))
        bullets.append(
            "- pre-state.txt: absent"
            if pre_state is None
            else f"- Pre-state: {json.dumps(pre_state.rstrip(chr(10) + chr(13)), ensure_ascii=False)}"
        )
    except InputError as error:
        print(f"turn-record: {error.path}: {error.reason}", file=sys.stderr)
        return 2

    print("\n".join(bullets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
