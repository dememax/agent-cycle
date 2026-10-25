#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Install a commit-pinned public-content gate outside its work tree — agent-cycle project

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

EXIT_REFUSAL = 2
INSTALLED_FILES = ("check-public.sh", "check-public.py", "pre-push")
OBJECT_NAME = re.compile(rb"[0-9a-f]{40}|[0-9a-f]{64}")


class Refusal(Exception):
    """A condition under which installation cannot safely continue."""


def git(repository: Path, arguments: Sequence[str]) -> bytes:
    """Run one Git query and replace all failures with a stable refusal."""
    try:
        result = subprocess.run(
            ["git", "-C", repository, *arguments],
            env=os.environ | {"GIT_OPTIONAL_LOCKS": "0"},
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise Refusal("Git command could not run") from error
    if result.returncode != 0:
        raise Refusal("Git command failed")
    return result.stdout


def repository_root(script_directory: Path) -> Path:
    """Find the work tree that contains this tracked installer."""
    output = git(script_directory, ["rev-parse", "--show-toplevel"])
    try:
        root = Path(output.decode("utf-8", errors="strict").strip()).resolve()
    except UnicodeError as error:
        raise Refusal("Git returned an invalid work-tree path") from error
    if not root.is_dir():
        raise Refusal("Git returned an invalid work-tree path")
    return root


def parse_arguments(argv: Sequence[str]) -> tuple[str, Path]:
    """Accept DEST, or --rev REV DEST, without ambiguous variants."""
    if len(argv) == 1:
        revision, destination = "HEAD", argv[0]
    elif len(argv) == 3 and argv[0] == "--rev" and argv[1]:
        revision, destination = argv[1], argv[2]
    else:
        raise Refusal("usage: install-gate.sh [--rev REV] DEST")
    if not destination:
        raise Refusal("destination is empty")
    return revision, Path(destination).expanduser().resolve()


def resolved_commit(repository: Path, revision: str) -> str:
    """Resolve the requested revision to one full commit object name."""
    output = git(repository, ["rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"])
    value = output.strip()
    if OBJECT_NAME.fullmatch(value) is None:
        raise Refusal("Git returned an invalid revision")
    return value.decode("ascii")


def validate_destination(repository: Path, destination: Path) -> None:
    """Require an external path that is absent or an empty directory."""
    if destination == repository or repository in destination.parents:
        raise Refusal("destination is inside the repository work tree")
    if not destination.exists():
        return
    try:
        if not destination.is_dir() or any(destination.iterdir()):
            raise Refusal("destination exists and is not empty")
    except OSError as error:
        raise Refusal("destination cannot be inspected") from error


def committed_files(repository: Path, commit: str) -> dict[str, bytes]:
    """Read all runtime files from the selected commit, never from the work tree."""
    return {name: git(repository, ["show", f"{commit}:tools/{name}"]) for name in INSTALLED_FILES}


def install(destination: Path, commit: str, contents: dict[str, bytes]) -> None:
    """Write the runtime files and their verifiable provenance metadata."""
    created: list[Path] = []
    try:
        destination.mkdir(parents=True, exist_ok=True)
        sums: list[str] = []
        for name in INSTALLED_FILES:
            target = destination / name
            with target.open("xb") as stream:
                stream.write(contents[name])
            created.append(target)
            target.chmod(0o755)
            sums.append(f"{hashlib.sha256(contents[name]).hexdigest()}  {name}")
        sums_path = destination / "SHA256SUMS"
        sums_path.write_text("\n".join(sums) + "\n", encoding="ascii", errors="strict")
        created.append(sums_path)
        revision_path = destination / "REVISION"
        revision_path.write_text(commit + "\n", encoding="ascii", errors="strict")
        created.append(revision_path)
    except OSError as error:
        for path in created:
            with suppress(OSError):
                path.unlink(missing_ok=True)
        raise Refusal("destination cannot be written") from error


def main(argv: Sequence[str]) -> int:
    """Install one immutable gate version and print, but do not run, its setup command."""
    try:
        revision, destination = parse_arguments(argv)
        repository = repository_root(Path(__file__).resolve().parent)
        validate_destination(repository, destination)
        commit = resolved_commit(repository, revision)
        contents = committed_files(repository, commit)
        install(destination, commit, contents)
    except Refusal as error:
        print(f"install-gate: refused: {error}", file=sys.stderr)
        return EXIT_REFUSAL
    print(f"git config core.hooksPath {shlex.quote(str(destination))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
