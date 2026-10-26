# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box characterization of Git repository snapshots — agent-cycle project

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
from typing import TYPE_CHECKING

import pytest

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


def failing_git(isolated_env: IsolatedEnvironment) -> Path:
    """Put a generated selectively failing Git delegate in the fake home."""
    directory = isolated_env.home / "fake-bin"
    directory.mkdir()
    wrapper = directory / "git"
    wrapper.write_text(
        """#!/usr/bin/env python3.14
import os
import sys

arguments = sys.argv[1:]
repository = arguments[arguments.index("-C") + 1] if "-C" in arguments else ""
step = ""
if "rev-parse" in arguments and any(argument.startswith("HEAD") for argument in arguments):
    step = "HEAD"
elif "for-each-ref" in arguments and "refs/codex" in arguments:
    step = "refs/codex"
elif "for-each-ref" in arguments:
    step = "refs"
elif "status" in arguments:
    step = "status"
if step == os.environ.get("SNAPSHOT_FAIL_STEP") and repository == os.environ.get("SNAPSHOT_FAIL_REPO"):
    sys.stderr.write(os.environ["SNAPSHOT_GIT_ERROR"] + "\\n")
    raise SystemExit(73)
real_git = os.environ["SNAPSHOT_REAL_GIT"]
os.execv(real_git, [real_git, *arguments])
""",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def blocking_git(isolated_env: IsolatedEnvironment) -> Path:
    """Put a generated Git delegate with a FIFO-controlled blocking step on PATH."""
    directory = isolated_env.home / "blocking-bin"
    directory.mkdir()
    wrapper = directory / "git"
    wrapper.write_text(
        """#!/usr/bin/env python3.14
import os
import sys

arguments = sys.argv[1:]
repository = arguments[arguments.index("-C") + 1] if "-C" in arguments else ""
if (
    repository == os.environ["SNAPSHOT_BLOCK_REPO"]
    and "rev-parse" in arguments
    and any(argument.startswith("HEAD") for argument in arguments)
):
    with open(os.environ["SNAPSHOT_READY_FIFO"], "w", encoding="ascii") as ready:
        ready.write("ready\\n")
        ready.flush()
    with open(os.environ["SNAPSHOT_RELEASE_FIFO"], encoding="ascii") as release:
        release.read(1)
real_git = os.environ["SNAPSHOT_REAL_GIT"]
os.execv(real_git, [real_git, *arguments])
""",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    return wrapper


def snapshot_result(
    isolated_env: IsolatedEnvironment,
    *,
    failing_repository: Path | None = None,
    failing_step: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a snapshot, optionally injecting one repository-local Git failure."""
    extra_env: dict[str, str] = {}
    if failing_repository is not None and failing_step is not None:
        wrapper = failing_git(isolated_env)
        real_git = shutil.which("git")
        assert real_git is not None
        extra_env = {
            "PATH": str(wrapper.parent) + os.pathsep + isolated_env.variables["PATH"],
            "SNAPSHOT_REAL_GIT": real_git,
            "SNAPSHOT_FAIL_REPO": str(failing_repository),
            "SNAPSHOT_FAIL_STEP": failing_step,
            "SNAPSHOT_GIT_ERROR": "generated Git diagnostic that must stay hidden",
        }
    return isolated_env.run([SNAPSHOT], extra_env=extra_env)


@pytest.mark.parametrize("signal_number", [signal.SIGHUP, signal.SIGINT, signal.SIGQUIT, signal.SIGTERM])
def test_snapshot_signal_exits_and_removes_temporary_file(
    isolated_env: IsolatedEnvironment,
    signal_number: signal.Signals,
) -> None:
    """An interrupted Git step cannot continue into a complete-looking snapshot."""
    blocked = isolated_env.home / "github" / "a-blocked"
    not_reached = isolated_env.home / "github" / "z-not-reached"
    initialize(isolated_env, blocked, commit=True)
    initialize(isolated_env, not_reached, commit=True)
    temporary_directory = isolated_env.home.parent / "tmp"
    temporary_directory.mkdir()
    ready_fifo = isolated_env.home.parent / "ready.fifo"
    release_fifo = isolated_env.home.parent / "release.fifo"
    os.mkfifo(ready_fifo)
    os.mkfifo(release_fifo)
    wrapper = blocking_git(isolated_env)
    real_git = shutil.which("git")
    assert real_git is not None
    environment = isolated_env.variables | {
        "PATH": str(wrapper.parent) + os.pathsep + isolated_env.variables["PATH"],
        "SNAPSHOT_REAL_GIT": real_git,
        "SNAPSHOT_BLOCK_REPO": str(blocked),
        "SNAPSHOT_READY_FIFO": str(ready_fifo),
        "SNAPSHOT_RELEASE_FIFO": str(release_fifo),
        "TMPDIR": str(temporary_directory),
    }

    process = subprocess.Popen(
        [SNAPSHOT],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    with ready_fifo.open(encoding="ascii") as ready:
        assert ready.readline() == "ready\n"
    process.send_signal(signal_number)
    with release_fifo.open("w", encoding="ascii") as release:
        release.write("x")
    stdout, _stderr = process.communicate(timeout=10)

    assert process.returncode == 128 + signal_number
    assert str(not_reached) not in stdout
    assert not list(temporary_directory.glob("agent-cycle-snapshot.*"))


def test_snapshot_normal_run_removes_temporary_file(isolated_env: IsolatedEnvironment) -> None:
    """The EXIT trap removes its temporary file after a complete snapshot."""
    repo = isolated_env.home / "github" / "complete"
    initialize(isolated_env, repo, commit=True)
    temporary_directory = isolated_env.home.parent / "tmp"
    temporary_directory.mkdir()

    result = isolated_env.run([SNAPSHOT], extra_env={"TMPDIR": str(temporary_directory)})

    assert result.returncode == 0, result.stderr
    assert not list(temporary_directory.glob("agent-cycle-snapshot.*"))


@pytest.mark.parametrize(
    ("failing_step", "diagnostic_step"),
    [
        ("HEAD", "HEAD"),
        ("refs", "refs"),
        ("refs/codex", "refs/codex"),
        ("status", "status"),
    ],
)
def test_snapshot_refuses_each_git_failure_without_echoing_git_output(
    isolated_env: IsolatedEnvironment,
    failing_step: str,
    diagnostic_step: str,
) -> None:
    """Every Git query is checked before its result contributes to a line."""
    repo = isolated_env.home / "github" / "failing"
    initialize(isolated_env, repo, commit=True)

    result = snapshot_result(
        isolated_env,
        failing_repository=repo,
        failing_step=failing_step,
    )

    assert result.returncode == 2
    assert str(repo) in result.stderr
    assert diagnostic_step in result.stderr
    assert "generated Git diagnostic" not in result.stdout + result.stderr
    assert str(repo) not in result.stdout


def test_snapshot_accepts_an_unborn_symbolic_branch(isolated_env: IsolatedEnvironment) -> None:
    """A valid symbolic HEAD whose branch does not exist is an empty repository."""
    repo = isolated_env.home / "github" / "unborn"
    initialize(isolated_env, repo, commit=False)

    result = snapshot_result(isolated_env)

    assert result.returncode == 0, result.stderr
    match = LINE.fullmatch(result.stdout.strip())
    assert match is not None
    assert match.group("path") == str(repo)
    assert match.group("head") == "none"


def test_snapshot_refuses_an_unresolvable_detached_head(isolated_env: IsolatedEnvironment) -> None:
    """An object name missing from the repository is not an unborn branch."""
    repo = isolated_env.home / "github" / "broken-head"
    initialize(isolated_env, repo, commit=True)
    (repo / ".git" / "HEAD").write_text("f" * 40 + "\n", encoding="ascii")

    result = snapshot_result(isolated_env)

    assert result.returncode == 2
    assert str(repo) in result.stderr
    assert "HEAD" in result.stderr
    assert str(repo) not in result.stdout


def test_snapshot_keeps_good_repository_line_when_another_fails(
    isolated_env: IsolatedEnvironment,
) -> None:
    """One failed repository sets the exit status without suppressing complete peers."""
    good = isolated_env.home / "github" / "good"
    bad = isolated_env.home / "github" / "bad"
    initialize(isolated_env, good, commit=True)
    initialize(isolated_env, bad, commit=True)
    baseline = snapshot_result(isolated_env)
    assert baseline.returncode == 0, baseline.stderr
    good_line = next(line for line in baseline.stdout.splitlines() if line.startswith(str(good) + " "))

    result = snapshot_result(
        isolated_env,
        failing_repository=bad,
        failing_step="status",
    )

    assert result.returncode == 2
    assert good_line in result.stdout.splitlines()
    assert not any(line.startswith(str(bad) + " ") for line in result.stdout.splitlines())
    assert str(bad) in result.stderr


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
