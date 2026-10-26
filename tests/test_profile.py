# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box tests for strict project-profile loading — agent-cycle project

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from .conftest import PYTHON, ROOT, IsolatedEnvironment

if TYPE_CHECKING:
    from pathlib import Path

PROBE = ROOT / "tests" / "codexlog_probe.py"
RETIRED_VARIABLES = ("AGENT_CYCLE_REPO", "AGENT_CYCLE_STATE", "S0_STATE_DIR")


def write_profile(path: Path, content: str) -> None:
    """Write one generated profile case."""
    path.write_text(content, encoding="utf-8")


def run_profile(
    isolated_env: IsolatedEnvironment,
    *,
    extra_env: dict[str, str] | None = None,
    unset_env: tuple[str, ...] = RETIRED_VARIABLES,
) -> tuple[int, str, str]:
    """Load a profile without permitting retired selectors to leak in."""
    result = isolated_env.run(
        [PYTHON, "-I", PROBE, "profile", "unused"],
        extra_env=extra_env,
        unset_env=unset_env,
    )
    return result.returncode, result.stdout, result.stderr


def test_valid_profile_selects_repository_and_state(isolated_env: IsolatedEnvironment) -> None:
    """All three profile fields are returned from one selected file."""
    code, stdout, stderr = run_profile(isolated_env)

    assert code == 0, stderr
    assert json.loads(stdout) == {
        "name": "generated",
        "repository": str(isolated_env.repo),
        "state": str(isolated_env.state),
    }


def test_tilde_paths_expand_only_against_home(isolated_env: IsolatedEnvironment) -> None:
    """The supported portable path spelling uses the isolated HOME."""
    write_profile(
        isolated_env.profile,
        'profile_version = 1\nname = "tilde"\nrepository = "~/repo"\nstate = "~/.state"\n',
    )

    code, stdout, stderr = run_profile(isolated_env)

    assert code == 0, stderr
    assert json.loads(stdout) == {
        "name": "tilde",
        "repository": str(isolated_env.home / "repo"),
        "state": str(isolated_env.home / ".state"),
    }


@pytest.mark.parametrize(
    "value",
    ["~//etc", "/a//b", "/a/./b", "/a/../b", "~/a/../b", "~/./a", "/a/", "~/a/"],
    ids=[
        "tilde-empty-component",
        "absolute-empty-component",
        "absolute-dot-component",
        "absolute-dot-dot-component",
        "tilde-dot-dot-component",
        "tilde-dot-component",
        "absolute-trailing-slash",
        "tilde-trailing-slash",
    ],
)
def test_profile_path_requires_canonical_spelling(
    isolated_env: IsolatedEnvironment,
    value: str,
) -> None:
    """Profile paths cannot change meaning during Path construction."""
    write_profile(
        isolated_env.profile,
        f'profile_version = 1\nname = "x"\nrepository = {json.dumps(value)}\nstate = "/state"\n',
    )

    code, stdout, stderr = run_profile(isolated_env)

    assert code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert str(isolated_env.profile) in stderr
    assert "repository" in stderr
    assert 'expected a canonical path (no empty, "." or ".." component, no trailing "/")' in stderr


@pytest.mark.parametrize("value", [None, "", "relative/profile.toml"], ids=["unset", "empty", "relative"])
def test_profile_selector_is_required_and_absolute(
    isolated_env: IsolatedEnvironment,
    value: str | None,
) -> None:
    """There is no default profile or relative profile lookup."""
    extra_env = {} if value is None else {"AGENT_CYCLE_PROFILE": value}
    unset_env = (*RETIRED_VARIABLES, "AGENT_CYCLE_PROFILE") if value is None else RETIRED_VARIABLES

    code, stdout, stderr = run_profile(isolated_env, extra_env=extra_env, unset_env=unset_env)

    assert code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert "AGENT_CYCLE_PROFILE" in stderr
    assert ("unset" if value is None else "absolute") in stderr


@pytest.mark.parametrize("variable", RETIRED_VARIABLES)
def test_retired_selector_is_refused(isolated_env: IsolatedEnvironment, variable: str) -> None:
    """A stale selector fails loudly instead of being ignored."""
    code, stdout, stderr = run_profile(
        isolated_env,
        extra_env={variable: "/generated/stale"},
        unset_env=tuple(item for item in RETIRED_VARIABLES if item != variable),
    )

    assert code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert variable in stderr
    assert "retired" in stderr


@pytest.mark.parametrize(
    ("content", "key", "message"),
    [
        ('profile_version = 1\nname = "x"\nrepository = "/repo"\n', "state", "missing"),
        (
            'profile_version = 1\nname = "x"\nrepository = "/repo"\nstate = "/state"\nextra = true\n',
            "extra",
            "unknown",
        ),
        ('profile_version = 3\nname = "x"\nrepository = "/repo"\nstate = "/state"\n', "profile_version", "1"),
        ('profile_version = true\nname = "x"\nrepository = "/repo"\nstate = "/state"\n', "profile_version", "1"),
        ('profile_version = 1\nname = ""\nrepository = "/repo"\nstate = "/state"\n', "name", "non-empty"),
        ('profile_version = 1\nname = 3\nrepository = "/repo"\nstate = "/state"\n', "name", "non-empty"),
        (
            'profile_version = 1\nname = "x"\nrepository = "relative"\nstate = "/state"\n',
            "repository",
            "absolute or start",
        ),
        (
            'profile_version = 1\nname = "x"\nrepository = "/repo"\nstate = "~other/state"\n',
            "state",
            "absolute or start",
        ),
    ],
    ids=[
        "missing",
        "unknown",
        "version",
        "version-wrong-type",
        "empty-name",
        "name-wrong-type",
        "relative-repository",
        "unsupported-tilde-state",
    ],
)
def test_profile_content_is_strict(
    isolated_env: IsolatedEnvironment,
    content: str,
    key: str,
    message: str,
) -> None:
    """Missing, extra, ill-typed and invalid values are configuration errors."""
    write_profile(isolated_env.profile, content)

    code, stdout, stderr = run_profile(isolated_env)

    assert code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert str(isolated_env.profile) in stderr
    assert key in stderr
    assert message in stderr


@pytest.mark.parametrize("case", ["unreadable", "invalid-toml"])
def test_unreadable_or_invalid_profile_is_refused(
    isolated_env: IsolatedEnvironment,
    case: str,
) -> None:
    """I/O and TOML failures remain one-line configuration errors."""
    if case == "unreadable":
        isolated_env.profile.unlink()
        isolated_env.profile.mkdir()
    else:
        write_profile(isolated_env.profile, "profile_version = [\n")

    code, stdout, stderr = run_profile(isolated_env)

    assert code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert str(isolated_env.profile) in stderr
    assert "profile" in stderr
