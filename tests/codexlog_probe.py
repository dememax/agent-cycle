# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Subprocess entry point for strict-reader characterization — agent-cycle project

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CODEXLOG = runpy.run_path(str(ROOT / "bin" / "codexlog.py"))


def main() -> int:
    """Invoke one reader operation and serialize its result."""
    operation = sys.argv[1]
    argument = sys.argv[2]
    functions: dict[str, Any] = CODEXLOG
    if operation == "profile":
        try:
            profile = functions["load_project_profile"]()
        except functions["ProfileError"] as error:
            print(f"profile-probe: configuration error: {error}", file=sys.stderr)
            return 2
        result = {
            "name": profile.name,
            "repository": str(profile.repository),
            "state": str(profile.state),
        }
    elif operation == "canonical":
        result = functions["canonical"](argument)
    else:
        records = functions["records"](Path(argument))
        if operation == "records":
            result = len(records)
        elif operation == "session_meta":
            result = functions["session_meta"](records)
        elif operation == "messages":
            result = functions["composer_messages"](records)
        elif operation == "initial":
            result = functions["initial_composer"](records)
        elif operation == "running":
            result = functions["running_turns"](records)
        else:
            raise ValueError(f"unknown operation: {operation}")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
