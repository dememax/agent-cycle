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
    fake_codex: Path
    variables: dict[str, str]

    def run(
        self,
        arguments: Sequence[str | Path],
        *,
        extra_env: Mapping[str, str] | None = None,
        timeout: float = 10,
    ) -> subprocess.CompletedProcess[str]:
        """Run a command with the mandatory isolated environment."""
        environment = self.variables | dict(extra_env or {})
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
    variables = dict(os.environ)
    variables.update(
        {
            "HOME": str(home),
            "CODEX": str(fake_codex),
            "AGENT_CYCLE_REPO": str(repo),
            "AGENT_CYCLE_STATE": str(state),
            "S0_QUEUE_TIMEOUT": "0.05",
        }
    )
    variables.pop("S0_STATE_DIR", None)
    return IsolatedEnvironment(home, repo, state, fake_codex, variables)
