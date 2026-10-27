#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Generated restart-state cache — agent-cycle project
"""Print or write the current generated project-state summary.

Usage: state.py [--write]
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codexlog

AUDIT_EXIT = re.compile(r"audit exit -?[0-9]+")
TURN_DIRECTORY = re.compile(r"turn-([0-9]+)")

type Fact = dict[str, Any]
type Source = dict[str, str]


class StateError(ValueError):
    """An invocation or active record cannot be interpreted safely."""


def local_mtime(path: Path) -> str:
    """Render a filesystem modification time in the process's local zone."""
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def path_source(path: Path) -> Source:
    """Identify an existing path, or the parent observation for an absent path."""
    try:
        return {"path": str(path), "modified_at": local_mtime(path)}
    except OSError:
        try:
            observed = local_mtime(path.parent)
        except OSError:
            observed = "unknown"
        return {"path": str(path), "parent_modified_at": observed}


def known(value: object, source: Source) -> Fact:
    """Represent one known fact and its source."""
    return {"value": value, "source": source}


def unknown(reason: str, source: Source) -> Fact:
    """Represent one unavailable fact without inventing a value."""
    return {"value": None, "unknown": reason, "source": source}


def command_source(
    repository: Path, arguments: tuple[str, ...], completed: subprocess.CompletedProcess[bytes]
) -> Source:
    """Fingerprint the complete Git query that supplied one repository fact."""
    digest = hashlib.sha256()
    for part in (*arguments, str(completed.returncode)):
        digest.update(part.encode())
        digest.update(b"\0")
    digest.update(completed.stdout)
    digest.update(b"\0")
    digest.update(completed.stderr)
    return {"path": str(repository), "sha256": digest.hexdigest()}


def git_fact(
    repository: Path,
    arguments: tuple[str, ...],
    convert: Callable[[bytes], object] | None = None,
) -> Fact:
    """Read one Git fact, retaining failures as an unknown value."""
    command = ("git", "--no-optional-locks", "-C", str(repository), *arguments)
    try:
        completed = subprocess.run(command, capture_output=True, check=False)
    except OSError as error:
        source = {"path": str(repository), "sha256": hashlib.sha256(repr(command).encode()).hexdigest()}
        return unknown(f"cannot run git ({error})", source)
    source = command_source(repository, arguments, completed)
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        reason = f"git {' '.join(arguments)} exited {completed.returncode}"
        return unknown(f"{reason}: {detail}" if detail else reason, source)
    try:
        value = convert(completed.stdout) if convert is not None else completed.stdout.decode().strip()
    except (UnicodeError, ValueError) as error:
        return unknown(f"cannot interpret git output ({error})", source)
    return known(value, source)


def repository_facts(repository: Path) -> dict[str, Fact]:
    """Read the local repository only; never contact its remote."""
    head = git_fact(repository, ("rev-parse", "--verify", "HEAD"))
    branch = git_fact(repository, ("symbolic-ref", "--quiet", "--short", "HEAD"))
    dirty = git_fact(
        repository,
        ("status", "--porcelain=v1", "-uall"),
        lambda output: len(output.splitlines()),
    )
    branch_name = branch["value"]
    if isinstance(branch_name, str):
        remote = f"refs/remotes/origin/{branch_name}"
        origin = git_fact(repository, ("rev-parse", "--verify", remote))
        ahead = git_fact(repository, ("rev-list", "--count", f"{remote}..HEAD"), lambda output: int(output))
    else:
        reason = "current branch is unknown"
        origin = unknown(reason, branch["source"])
        ahead = unknown(reason, branch["source"])
    return {
        "head": head,
        "branch": branch,
        "origin_ref": origin,
        "dirty_entries": dirty,
        "ahead_of_origin": ahead,
    }


def active_record(state: Path) -> tuple[dict[str, Fact], Path | None]:
    """Read the active record; missing is unknown, malformed is an error."""
    path = state / "active-codex-thread.json"
    source = path_source(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        reason = "active-codex-thread.json is absent"
        return {key: unknown(reason, source) for key in ("thread_id", "log_path", "sentinel")}, None
    except OSError as error:
        reason = f"active-codex-thread.json cannot be read ({error})"
        return {key: unknown(reason, source) for key in ("thread_id", "log_path", "sentinel")}, None
    try:
        record = json.loads(text)
    except ValueError as error:
        raise StateError(f"active-codex-thread.json: unparseable JSON ({error})") from None
    if not isinstance(record, dict):
        raise StateError("active-codex-thread.json: unparseable: expected an object")
    values: dict[str, str] = {}
    for key in ("thread_id", "log_path", "sentinel"):
        value = record.get(key)
        if not isinstance(value, str) or not value:
            raise StateError(f"active-codex-thread.json: unparseable {key}: expected a non-empty string")
        values[key] = value
    log = Path(values["log_path"])
    if not log.is_absolute():
        raise StateError("active-codex-thread.json: unparseable log_path: expected an absolute path")
    return {key: known(value, source) for key, value in values.items()}, log


def log_unknowns(reason: str, source: Source) -> tuple[dict[str, Fact], dict[str, Fact]]:
    """Invalidate all facts derived from one unreadable strict log."""
    thread = {key: unknown(reason, source) for key in ("turns", "running", "compacted_records")}
    rates = {
        key: unknown(reason, source)
        for key in (
            "five_hour_used_percent",
            "five_hour_resets_at",
            "weekly_used_percent",
            "weekly_resets_at",
        )
    }
    return thread, rates


def number(value: object) -> int | float | None:
    """Accept JSON numbers but not booleans."""
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def reset_time(value: object) -> str | None:
    """Render a Unix reset timestamp in the process's local zone."""
    stamp = number(value)
    if stamp is None:
        return None
    try:
        return datetime.fromtimestamp(stamp).astimezone().isoformat(timespec="seconds")
    except OSError, OverflowError, ValueError:
        return None


def rate_facts(records: list[dict[str, Any]], source: Source) -> dict[str, Fact]:
    """Read the newest Codex rate-limit entry from a strict rollout."""
    latest: dict[str, Any] | None = None
    for record in reversed(records):
        payload = record.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        limits = payload.get("rate_limits")
        if isinstance(limits, dict) and limits.get("limit_id") == "codex":
            latest = limits
            break
    names = (
        "five_hour_used_percent",
        "five_hour_resets_at",
        "weekly_used_percent",
        "weekly_resets_at",
    )
    if latest is None:
        return {name: unknown("no codex rate_limits entry", source) for name in names}
    primary = latest.get("primary")
    secondary = latest.get("secondary")
    primary = primary if isinstance(primary, dict) else {}
    secondary = secondary if isinstance(secondary, dict) else {}
    raw = {
        "five_hour_used_percent": number(primary.get("used_percent")),
        "five_hour_resets_at": reset_time(primary.get("resets_at")),
        "weekly_used_percent": number(secondary.get("used_percent")),
        "weekly_resets_at": reset_time(secondary.get("resets_at")),
    }
    return {
        name: known(value, source) if value is not None else unknown(f"latest codex rate_limits lacks {name}", source)
        for name, value in raw.items()
    }


def log_facts(log: Path | None, active_source: Source) -> tuple[dict[str, Fact], dict[str, Fact]]:
    """Read all log-derived facts from one all-or-nothing strict parse."""
    if log is None:
        return log_unknowns("active log path is unknown", active_source)
    source = path_source(log)
    try:
        records = codexlog.records(log)
        states = codexlog.turn_states(records)
        running = codexlog.running_turns(records)
    except (OSError, codexlog.LogError) as error:
        return log_unknowns(f"cannot read strict log ({error})", source)
    thread = {
        "turns": known(len(states), source),
        "running": known(bool(running), source),
        "compacted_records": known(sum(record.get("type") == "compacted" for record in records), source),
    }
    return thread, rate_facts(records, source)


def pending_fact(state: Path) -> Fact:
    """Report only whether the queue's durable pending marker exists."""
    path = state / "pending.json"
    try:
        path.stat()
    except FileNotFoundError:
        return known(False, path_source(path))
    except OSError as error:
        return unknown(f"pending marker cannot be checked ({error})", path_source(path))
    return known(True, path_source(path))


def file_text_fact(path: Path, description: str) -> Fact:
    """Read one optional text fact without guessing absent or empty content."""
    source = path_source(path)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return unknown(f"{description} is absent", source)
    except OSError as error:
        return unknown(f"{description} cannot be read ({error})", source)
    return known(text, source) if text else unknown(f"{description} is empty", source)


def newest_turn_facts(state: Path) -> dict[str, Fact]:
    """Select the highest numeric turn directory and read its completion facts."""
    state_source = path_source(state)
    try:
        candidates = []
        for path in state.iterdir():
            match = TURN_DIRECTORY.fullmatch(path.name)
            if match and path.is_dir():
                candidates.append((int(match.group(1)), path))
    except OSError as error:
        reason = f"state directory cannot be read ({error})"
        return {key: unknown(reason, state_source) for key in ("name", "finished", "audit_exit")}
    if not candidates:
        reason = "no numeric turn directory"
        return {key: unknown(reason, state_source) for key in ("name", "finished", "audit_exit")}
    _number, turn = max(candidates)
    name = known(turn.name, path_source(turn))
    finished = file_text_fact(turn / "finished", "finished marker")
    audit_path = turn / "audit.txt"
    audit_source = path_source(audit_path)
    try:
        lines = audit_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        audit = unknown("audit transcript is absent", audit_source)
    except OSError as error:
        audit = unknown(f"audit transcript cannot be read ({error})", audit_source)
    else:
        exits = [line for line in lines if AUDIT_EXIT.fullmatch(line)]
        audit = known(exits[-1], audit_source) if exits else unknown("audit exit line is absent", audit_source)
    return {"name": name, "finished": finished, "audit_exit": audit}


def notes_fact(state: Path) -> Fact:
    """Include driver notes byte-for-text, or record their absence explicitly."""
    path = state / "notes.md"
    source = path_source(path)
    try:
        return known(path.read_text(encoding="utf-8"), source)
    except FileNotFoundError:
        return known("absent", source)
    except OSError as error:
        return unknown(f"notes.md cannot be read ({error})", source)


def collect(profile: codexlog.ProjectProfile) -> dict[str, Any]:
    """Collect one internally consistent best-effort snapshot of current facts."""
    active, log = active_record(profile.state)
    active_source = active["log_path"]["source"]
    thread, rates = log_facts(log, active_source)
    return {
        "schema_version": 1,
        "repository": repository_facts(profile.repository),
        "active_thread": active,
        "thread": thread,
        "submission": {"pending": pending_fact(profile.state)},
        "rate_limits": rates,
        "newest_turn": newest_turn_facts(profile.state),
        "notes": {"content": notes_fact(profile.state)},
    }


def source_text(source: Source) -> str:
    """Render the one provenance annotation carried by a fact."""
    path = source["path"]
    for key, label in (
        ("modified_at", "modified"),
        ("parent_modified_at", "parent modified"),
        ("sha256", "SHA-256"),
    ):
        if key in source:
            return f"`{path}` ({label} `{source[key]}`)"
    return f"`{path}`"


def value_text(fact: Fact) -> str:
    """Render a known scalar or an explicit unknown reason."""
    if "unknown" in fact:
        return f"unknown ({fact['unknown']})"
    value = fact["value"]
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def fact_line(label: str, fact: Fact) -> str:
    """Render one Markdown list item with inline provenance."""
    return f"- {label}: {value_text(fact)}\n  Source: {source_text(fact['source'])}"


def render(data: dict[str, Any]) -> str:
    """Render the human restart summary, preserving notes verbatim."""
    repository = data["repository"]
    active = data["active_thread"]
    thread = data["thread"]
    rates = data["rate_limits"]
    turn = data["newest_turn"]
    notes = data["notes"]["content"]
    parts = [
        "# Generated agent-cycle state",
        "",
        "This is a generated cache; the named records remain authoritative.",
        "",
        "## Repository",
        "",
        fact_line("HEAD", repository["head"]),
        fact_line("Branch", repository["branch"]),
        fact_line("Local origin ref", repository["origin_ref"]),
        fact_line("Dirty entries", repository["dirty_entries"]),
        fact_line("Commits ahead of origin", repository["ahead_of_origin"]),
        "",
        "## Active thread",
        "",
        fact_line("Thread ID", active["thread_id"]),
        fact_line("Log path", active["log_path"]),
        fact_line("Sentinel", active["sentinel"]),
        fact_line("Turns", thread["turns"]),
        fact_line("Running", thread["running"]),
        fact_line("Compacted records", thread["compacted_records"]),
        fact_line("Submission pending", data["submission"]["pending"]),
        "",
        "## Codex rate limits",
        "",
        fact_line("5-hour used percent", rates["five_hour_used_percent"]),
        fact_line("5-hour resets at", rates["five_hour_resets_at"]),
        fact_line("Weekly used percent", rates["weekly_used_percent"]),
        fact_line("Weekly resets at", rates["weekly_resets_at"]),
        "",
        "## Newest turn",
        "",
        fact_line("Name", turn["name"]),
        fact_line("Finished", turn["finished"]),
        fact_line("Audit", turn["audit_exit"]),
        "",
        "## Driver notes",
        "",
    ]
    rendered = "\n".join(parts) + "\n"
    rendered += value_text(notes) if "unknown" in notes else str(notes["value"])
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered + f"Source: {source_text(notes['source'])}\n"


def atomic_write(path: Path, content: str) -> None:
    """Publish one UTF-8 cache file by an fsynced same-directory rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(arguments: list[str]) -> int:
    """Collect state, optionally publish both caches, and print Markdown."""
    if arguments not in ([], ["--write"]):
        print("state: usage: state.py [--write]", file=sys.stderr)
        return 2
    try:
        profile = codexlog.load_project_profile()
        data = collect(profile)
    except codexlog.ProfileError as error:
        print(f"state: configuration error: {error}", file=sys.stderr)
        return 2
    except StateError as error:
        print(f"state: {error}", file=sys.stderr)
        return 2
    markdown = render(data)
    if arguments == ["--write"]:
        try:
            atomic_write(profile.state / "STATE.json", json.dumps(data, indent=2) + "\n")
            atomic_write(profile.state / "STATE.md", markdown)
        except OSError as error:
            print(f"state: cannot write cache ({error})", file=sys.stderr)
            return 2
    sys.stdout.write(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
