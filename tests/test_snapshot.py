# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box characterization of Git repository snapshots — agent-cycle project

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from .conftest import ROOT, IsolatedEnvironment

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

SNAPSHOT = ROOT / "bin" / "github-snapshot.sh"
LINE = re.compile(
    r"^(?P<path>.+) head=(?P<head>[0-9a-f]{40}|none) refs=(?P<refs>[0-9a-f]{16}) "
    r"codex_refs=(?P<codex>[0-9]+) status=(?P<status>[0-9a-f]{16})$"
)


def git(isolated_env: IsolatedEnvironment, repo: Path, arguments: Sequence[str]) -> str:
    """Run local-only Git against a generated repository."""
    environment = {
        "GIT_AUTHOR_NAME": "Generated Author",
        "GIT_AUTHOR_EMAIL": "generated",
        "GIT_COMMITTER_NAME": "Generated Committer",
        "GIT_COMMITTER_EMAIL": "generated",
    }
    result = isolated_env.run(["git", "-C", repo, *arguments], extra_env=environment)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def initialize(isolated_env: IsolatedEnvironment, repo: Path, *, commit: bool) -> None:
    """Create a local generated repository, optionally with one commit."""
    repo.mkdir(parents=True)
    git(isolated_env, repo, ["init", "-q"])
    if commit:
        (repo / "tracked.txt").write_text("generated\n", encoding="utf-8")
        git(isolated_env, repo, ["add", "tracked.txt"])
        git(isolated_env, repo, ["commit", "-q", "-m", "generated initial commit"])


def snapshot(isolated_env: IsolatedEnvironment) -> dict[str, dict[str, str]]:
    """Run the snapshot and parse its stable one-line records."""
    result = isolated_env.run([SNAPSHOT])
    assert result.returncode == 0, result.stderr
    parsed: dict[str, dict[str, str]] = {}
    for line in result.stdout.splitlines():
        match = LINE.fullmatch(line)
        assert match is not None, line
        values = match.groupdict()
        parsed[values.pop("path")] = values
    return parsed


def test_snapshot_format_hashes_depth_and_read_only_index(
    isolated_env: IsolatedEnvironment,
) -> None:
    """Snapshots separate refs, expose status, scan two depths and leave the index untouched."""
    top = isolated_env.home / "github" / "top"
    nested = isolated_env.home / "github" / "group" / "nested"
    initialize(isolated_env, top, commit=True)
    initialize(isolated_env, nested, commit=False)
    index = top / ".git" / "index"
    old_time = 946_684_800
    os.utime(index, (old_time, old_time))
    index_before = (index.read_bytes(), index.stat().st_mtime_ns)

    first = snapshot(isolated_env)

    assert set(first) == {str(top), str(nested)}
    assert re.fullmatch(r"[0-9a-f]{40}", first[str(top)]["head"])
    assert first[str(nested)]["head"] == "none"
    assert first[str(top)]["codex"] == "0"
    assert (index.read_bytes(), index.stat().st_mtime_ns) == index_before

    original_refs = first[str(top)]["refs"]
    original_status = first[str(top)]["status"]
    git(isolated_env, top, ["update-ref", "refs/codex/generated", "HEAD"])
    with_codex_ref = snapshot(isolated_env)[str(top)]
    assert with_codex_ref["codex"] == "1"
    assert with_codex_ref["refs"] == original_refs

    git(isolated_env, top, ["update-ref", "refs/heads/generated-extra", "HEAD"])
    with_regular_ref = snapshot(isolated_env)[str(top)]
    assert with_regular_ref["refs"] != original_refs
    assert with_regular_ref["codex"] == "1"

    (top / "untracked.txt").write_text("generated untracked content\n", encoding="utf-8")
    dirty = snapshot(isolated_env)[str(top)]
    assert dirty["status"] != original_status
    assert (index.read_bytes(), index.stat().st_mtime_ns) == index_before
