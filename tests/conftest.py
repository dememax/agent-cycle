# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Shared isolation fixtures for subprocess tests — agent-cycle project

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
PYTHON = "python3.14"


@dataclass(frozen=True)
class IsolatedEnvironment:
    """Paths and environment that cannot address the user's Codex state."""

    home: Path
    repo: Path
    state: Path
    profile: Path
    fake_codex: Path
    variables: dict[str, str]

    def run(
        self,
        arguments: Sequence[str | Path],
        *,
        extra_env: Mapping[str, str] | None = None,
        unset_env: Sequence[str] = (),
        timeout: float = 10,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command with the mandatory isolated environment."""
        environment = self.variables | dict(extra_env or {})
        for variable in unset_env:
            environment.pop(variable, None)
        return subprocess.run(
            [str(argument) for argument in arguments],
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )


@pytest.fixture
def isolated_env(tmp_path: Path) -> IsolatedEnvironment:
    """Provide a fake home, CLI, project and state for every subprocess."""
    home = tmp_path / "home"
    repo = tmp_path / "project"
    state = tmp_path / "state"
    for directory in (home, repo, state):
        directory.mkdir()
    fake_codex = ROOT / "tests" / "fakecodex.py"
    profile = tmp_path / "profile.toml"
    profile.write_text(
        f'profile_version = 1\nname = "generated"\nrepository = "{repo}"\nstate = "{state}"\n',
        encoding="utf-8",
    )
    variables = dict(os.environ)
    variables.update(
        {
            "HOME": str(home),
            "CODEX": str(fake_codex),
            "AGENT_CYCLE_PROFILE": str(profile),
            "S0_QUEUE_TIMEOUT": "0.5",
        }
    )
    for retired in ("AGENT_CYCLE_REPO", "AGENT_CYCLE_STATE", "S0_STATE_DIR"):
        variables.pop(retired, None)
    return IsolatedEnvironment(home, repo, state, profile, fake_codex, variables)
