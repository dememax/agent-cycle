# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Release identity tests — agent-cycle project

from __future__ import annotations

import runpy
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_identity_has_one_version_source() -> None:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        configuration = tomllib.load(stream)

    assert "project" in configuration
    metadata = configuration["project"]
    assert metadata == {
        "name": "agent-cycle",
        "version": "0.1.0",
        "description": "Tools for a reviewer-implementer pair of AI agents.",
        "requires-python": ">=3.14",
        "license": "GPL-3.0-only",
        "authors": [{"name": "Maxime P. DEMENTYEV"}],
    }

    sphinx_configuration = runpy.run_path(str(ROOT / "docs" / "conf.py"))
    assert sphinx_configuration["project"] == metadata["name"]
    assert sphinx_configuration["version"] == metadata["version"]
    assert sphinx_configuration["release"] == metadata["version"]
    assert '"0.1.0"' not in (ROOT / "docs" / "conf.py").read_text()
