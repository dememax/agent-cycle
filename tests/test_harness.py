# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Tests for the generated-log harness's isolation — agent-cycle project

from __future__ import annotations

import json
from pathlib import Path

from .conftest import PYTHON, IsolatedEnvironment


def test_subprocess_environment_cannot_reach_real_home(isolated_env: IsolatedEnvironment) -> None:
    """The fixture redirects every route through which queueing finds Codex."""
    probe = isolated_env.run(
        [
            PYTHON,
            "-I",
            "-c",
            "import json, os; from pathlib import Path; "
            "print(json.dumps({'home': str(Path.home()), 'codex': os.environ['CODEX'], "
            "'profile': os.environ['AGENT_CYCLE_PROFILE']}))",
        ]
    )
    assert probe.returncode == 0, probe.stderr
    observed = json.loads(probe.stdout)
    assert observed == {
        "home": str(isolated_env.home),
        "codex": str(isolated_env.fake_codex),
        "profile": str(isolated_env.profile),
    }
    assert not (Path(observed["home"]) / ".codex").exists()
