#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Fail-closed scanner for material a Git push would publish — agent-cycle project

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

EXIT_FINDING = 1
EXIT_REFUSAL = 2
OBJECT_NAME = re.compile(rb"[0-9a-f]{40}|[0-9a-f]{64}")
PUSH_LINE_OBJECT = re.compile(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}")
HOME_PATH = re.compile(r"/(?:home|Users)/(?!<[^/>\r\n]+>)[^/\s]+")
EMAIL = re.compile(
    r"(?<![A-Za-z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
ACCOUNT_KEY = re.compile(
    r'(?<!\w)(?:"?(?:creator_user_id|creator_account_id|account_id|accountUuid|'
    r'organizationUuid|userID|user_id)"?)\s*(?::|=)\s*'
    r'(?:"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s,}\]\r\n]+)'
)
COAUTHOR_EMAILS = frozenset(("noreply@openai.com", "noreply@anthropic.com"))


class Refusal(Exception):
    """A configuration, input or Git failure that makes scanning unsafe."""


@dataclass(frozen=True)
class Rule:
    """One validated external deny-list entry."""

    number: int
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class Finding:
    """One rule found in one publication item."""

    rule: str
    offset: int


@dataclass(frozen=True)
class ScanSpec:
    """Arguments passed after `git rev-list` options."""

    arguments: tuple[str, ...]
    end_options: bool


def git(arguments: Sequence[str], *, absent: str | None = None) -> bytes:
    """Run one read-only Git query, replacing every failure with a safe refusal."""
    try:
        result = subprocess.run(
            ["git", *arguments],
            env=os.environ | {"GIT_OPTIONAL_LOCKS": "0"},
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise Refusal("Git command could not run") from error
    if result.returncode == 1 and absent is not None:
        raise Refusal(absent)
    if result.returncode != 0:
        raise Refusal("Git command failed")
    return result.stdout


def deny_list_path() -> Path:
    """Resolve the private deny-list without inspecting its parent directory."""
    configured = os.environ.get("AGENT_CYCLE_DENY_LIST")
    if configured:
        return Path(configured)
    return Path.home() / ".config" / "agent-cycle" / "deny-list"


def load_rules(path: Path) -> list[Rule]:
    """Load and validate the private rule file without echoing its values."""
    try:
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode) or mode & 0o444 == 0:
            raise Refusal("deny-list is missing or unreadable")
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise Refusal("deny-list is missing or unreadable") from error

    rules: list[Rule] = []
    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.startswith("#"):
            continue
        kind, separator, value = line.partition(":")
        if not separator or kind not in {"fixed-i", "word", "regex"} or not value:
            raise Refusal(f"invalid deny-list entry {number}")
        try:
            if kind == "fixed-i":
                pattern = re.compile(re.escape(value), re.IGNORECASE)
            elif kind == "word":
                pattern = re.compile(rf"(?<!\w){re.escape(value)}(?!\w)")
            else:
                pattern = re.compile(value)
        except re.error as error:
            raise Refusal(f"invalid regular expression at deny-list entry {number}") from error
        rules.append(Rule(number, pattern))
    if not rules:
        raise Refusal("deny-list has no entries")
    return rules


class Scanner:
    """Apply private and built-in rules while emitting disclosure-safe locations."""

    def __init__(self, rules: list[Rule], allowed_email: str) -> None:
        self.rules = rules
        self.allowed_emails = {allowed_email.casefold(), *(email.casefold() for email in COAUTHOR_EMAILS)}
        self.count = 0

    def findings(self, text: str) -> list[Finding]:
        """Return at most one finding per rule for one scanned item."""
        found: list[Finding] = []
        for rule in self.rules:
            match = rule.pattern.search(text)
            if match is not None:
                found.append(Finding(f"deny-list entry {rule.number}", match.start()))
        match = HOME_PATH.search(text)
        if match is not None:
            found.append(Finding("home path", match.start()))
        for email in EMAIL.finditer(text):
            if email.group().casefold() not in self.allowed_emails:
                found.append(Finding("email", email.start()))
                break
        match = ACCOUNT_KEY.search(text)
        if match is not None:
            found.append(Finding("account key", match.start()))
        return found

    def safe_path(self, path: str) -> str:
        """Render a path unless doing so would repeat protected text."""
        if self.findings(path):
            return "<redacted>"
        return path.encode("unicode_escape", errors="backslashreplace").decode("ascii")

    def scan(
        self,
        text: str,
        *,
        commit: str,
        kind: str,
        path: str | None = None,
        lines: bool = False,
    ) -> None:
        """Scan one item and print only its location and matching rule name."""
        for finding in self.findings(text):
            fields = ["finding", f"commit={commit}", f"kind={kind}"]
            if path is not None:
                fields.append(f"path={self.safe_path(path)}")
            if lines:
                fields.append(f"line={text.count(chr(10), 0, finding.offset) + 1}")
            fields.append(f"rule={finding.rule}")
            print(" ".join(fields))
            self.count += 1


def parse_rev_list_objects(output: bytes) -> list[tuple[str, str | None]]:
    """Parse `git rev-list --objects -z` without line-based path ambiguity."""
    tokens = output.rstrip(b"\0").split(b"\0") if output else []
    objects: list[tuple[str, str | None]] = []
    index = 0
    while index < len(tokens):
        object_name = tokens[index]
        if OBJECT_NAME.fullmatch(object_name) is None:
            raise Refusal("Git returned malformed object output")
        index += 1
        path = None
        if index < len(tokens) and tokens[index].startswith(b"path="):
            path = tokens[index][5:].decode("utf-8", errors="surrogateescape")
            index += 1
        objects.append((object_name.decode("ascii"), path))
    return objects


def rev_list(spec: ScanSpec, *options: str) -> bytes:
    """Run rev-list with explicit option termination where the caller permits it."""
    arguments = ["rev-list", *options]
    if spec.end_options:
        arguments.append("--end-of-options")
    arguments.extend(spec.arguments)
    return git(arguments)


def commits_for(spec: ScanSpec) -> list[str]:
    """List commits in stable introduction order."""
    output = rev_list(spec, "--reverse", "--topo-order")
    try:
        commits = output.decode("ascii").splitlines()
    except UnicodeError as error:
        raise Refusal("Git returned malformed commit output") from error
    if any(OBJECT_NAME.fullmatch(commit.encode("ascii")) is None for commit in commits):
        raise Refusal("Git returned malformed commit output")
    return commits


def parse_tree(output: bytes) -> list[tuple[str, str]]:
    """Return object names and paths from a recursive NUL-delimited tree listing."""
    entries: list[tuple[str, str]] = []
    for record in output.rstrip(b"\0").split(b"\0") if output else []:
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3 or OBJECT_NAME.fullmatch(fields[2]) is None:
            raise Refusal("Git returned malformed tree output")
        entries.append((fields[2].decode("ascii"), path.decode("utf-8", errors="surrogateescape")))
    return entries


def blob_locations(commits: list[str]) -> dict[str, tuple[str, str]]:
    """Map each reachable blob to its first in-range commit and one path."""
    locations: dict[str, tuple[str, str]] = {}
    for commit in commits:
        for object_name, path in parse_tree(git(["ls-tree", "-r", "-z", commit])):
            locations.setdefault(object_name, (commit, path))
    return locations


def changed_paths(commit: str) -> list[str]:
    """List path names recorded by one commit, including root and merge changes."""
    output = git(["diff-tree", "--root", "-r", "-m", "--no-commit-id", "--name-only", "-z", commit])
    return [path.decode("utf-8", errors="surrogateescape") for path in output.rstrip(b"\0").split(b"\0") if path]


def parse_identity(header: bytes, name: bytes) -> str:
    """Extract the complete person identity from a commit or tag header."""
    prefix = name + b" "
    for line in header.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :]
            identity, separator, _timestamp = value.rpartition(b" ")
            if not separator:
                raise Refusal("Git object has a malformed identity")
            identity, separator, _timestamp = identity.rpartition(b" ")
            if not separator:
                raise Refusal("Git object has a malformed identity")
            return identity.decode("utf-8", errors="surrogateescape")
    raise Refusal("Git object is missing an identity")


def scan_commit(scanner: Scanner, commit: str) -> None:
    """Scan a commit's complete message, both identities and changed path names."""
    raw = git(["cat-file", "commit", commit])
    header, separator, message = raw.partition(b"\n\n")
    if not separator:
        raise Refusal("Git returned a malformed commit")
    scanner.scan(message.decode("utf-8", errors="surrogateescape"), commit=commit, kind="message")
    scanner.scan(parse_identity(header, b"author"), commit=commit, kind="identity")
    scanner.scan(parse_identity(header, b"committer"), commit=commit, kind="identity")
    for path in changed_paths(commit):
        scanner.scan(path, commit=commit, kind="path", path=path)


def scan_spec(scanner: Scanner, spec: ScanSpec) -> None:
    """Scan every commit and every range-specific blob Git enumerates."""
    commits = commits_for(spec)
    for commit in commits:
        scan_commit(scanner, commit)

    locations = blob_locations(commits)
    objects = parse_rev_list_objects(rev_list(spec, "--objects", "-z"))
    for object_name, reported_path in objects:
        object_type = git(["cat-file", "-t", object_name]).strip()
        if object_type != b"blob":
            continue
        location = locations.get(object_name)
        commit = location[0] if location else (commits[0] if commits else object_name)
        path = reported_path or (location[1] if location else "<unknown>")
        content = git(["cat-file", "blob", object_name]).decode("utf-8", errors="surrogateescape")
        scanner.scan(content, commit=commit, kind="blob", path=path, lines=True)


def scan_tag(scanner: Scanner, object_name: str) -> None:
    """Scan an annotated tag's message and tagger identity."""
    raw = git(["cat-file", "tag", object_name])
    header, separator, message = raw.partition(b"\n\n")
    if not separator:
        raise Refusal("Git returned a malformed tag")
    scanner.scan(message.decode("utf-8", errors="surrogateescape"), commit=object_name, kind="tag")
    scanner.scan(parse_identity(header, b"tagger"), commit=object_name, kind="tag")


def is_zero_object(value: str) -> bool:
    """Return whether a validated object field is Git's all-zero sentinel."""
    return set(value) == {"0"}


def parse_pre_push(remote: str) -> tuple[list[ScanSpec], list[str]]:
    """Read and validate the complete pre-push protocol before scanning."""
    try:
        text = sys.stdin.buffer.read().decode("utf-8")
    except UnicodeError as error:
        raise Refusal("malformed pre-push input") from error
    specs: list[ScanSpec] = []
    tags: list[str] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise Refusal("malformed pre-push input")
        _local_ref, local_object, _remote_ref, remote_object = fields
        if PUSH_LINE_OBJECT.fullmatch(local_object) is None or PUSH_LINE_OBJECT.fullmatch(remote_object) is None:
            raise Refusal("malformed pre-push input")
        if len(local_object) != len(remote_object):
            raise Refusal("malformed pre-push input")
        if is_zero_object(local_object):
            continue
        object_type = git(["cat-file", "-t", local_object]).strip()
        if object_type == b"tag":
            tags.append(local_object.lower())
        if is_zero_object(remote_object):
            specs.append(ScanSpec((local_object, "--not", f"--remotes={remote}"), False))
        else:
            specs.append(ScanSpec((f"{remote_object}..{local_object}",), True))
    return specs, tags


def configured_email() -> str:
    """Read the repository-local or inherited Git identity allowed by policy."""
    value = (
        git(
            ["config", "--get", "user.email"],
            absent="repository user.email is missing",
        )
        .decode("utf-8", errors="strict")
        .strip()
    )
    if not value or EMAIL.fullmatch(value) is None:
        raise Refusal("repository user.email is missing or invalid")
    return value


def arguments(argv: Sequence[str]) -> tuple[list[ScanSpec], list[str]]:
    """Parse explicit range mode or the pre-push hook mode."""
    if argv and argv[0] == "--pre-push":
        if len(argv) != 2 or not argv[1]:
            raise Refusal("invalid pre-push invocation")
        return parse_pre_push(argv[1])
    if not argv or any(not revision or revision.startswith("-") for revision in argv):
        raise Refusal("at least one revision range is required")
    return [ScanSpec(tuple(argv), True)], []


def main(argv: Sequence[str]) -> int:
    """Validate configuration and scan all requested publication objects."""
    try:
        rules = load_rules(deny_list_path())
        specs, tags = arguments(argv)
        scanner = Scanner(rules, configured_email())
        for spec in specs:
            scan_spec(scanner, spec)
        for tag in dict.fromkeys(tags):
            scan_tag(scanner, tag)
    except Refusal as error:
        print(f"check-public: refused: {error}", file=sys.stderr)
        return EXIT_REFUSAL
    return EXIT_FINDING if scanner.count else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
