# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Generated-command tests for the project validation runner — agent-cycle project

from __future__ import annotations

import json
import shutil
import stat
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from .conftest import PYTHON, ROOT, IsolatedEnvironment

if TYPE_CHECKING:
    import subprocess

VALIDATE = ROOT / "bin" / "validate.py"
PROFILE_PROBE = ROOT / "tests" / "codexlog_probe.py"


def write_validation_profile(isolated_env: IsolatedEnvironment, steps: list[dict[str, object]]) -> None:
    """Write one version-2 profile with ordered generated validation steps."""
    lines = [
        "profile_version = 2",
        'name = "generated"',
        f"repository = {json.dumps(str(isolated_env.repo))}",
        f"state = {json.dumps(str(isolated_env.state))}",
    ]
    for step in steps:
        lines.extend(
            [
                "",
                "[[validation]]",
                f"name = {json.dumps(step['name'])}",
                f"arguments = {json.dumps(step['arguments'])}",
            ]
        )
        environment = step.get("environment")
        if environment is not None:
            assert isinstance(environment, dict)
            entries = ", ".join(f"{key} = {json.dumps(value)}" for key, value in environment.items())
            lines.append(f"environment = {{ {entries} }}")
        for flag in ("pytest", "always_show", "require_clean"):
            if flag in step:
                lines.append(f"{flag} = {'true' if step[flag] else 'false'}")
    isolated_env.profile.write_text("\n".join(lines) + "\n", encoding="utf-8")


def command(source: str, *arguments: str) -> list[str]:
    """Build a tiny generated Python command without shell syntax."""
    return [PYTHON, "-c", source, *arguments]


def run_validate(
    isolated_env: IsolatedEnvironment,
    *arguments: str | Path,
) -> subprocess.CompletedProcess[str]:
    """Run validation with the isolated profile and repository."""
    return isolated_env.run([PYTHON, VALIDATE, *arguments], timeout=30)


def test_isolated_mode_finds_shared_reader(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """The documented isolated invocation can import the adjacent reader."""
    write_validation_profile(
        isolated_env,
        [{"name": "step", "arguments": command("print('generated')")}],
    )

    result = isolated_env.run(
        [PYTHON, "-I", VALIDATE, "--out", tmp_path / "validation"],
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "step: exit 0" in result.stdout


def test_all_steps_pass_and_default_output_is_private(isolated_env: IsolatedEnvironment) -> None:
    write_validation_profile(
        isolated_env,
        [
            {
                "name": "pytest",
                "arguments": command(
                    "import os; print(os.environ['GENERATED_ENV']); print('=== 3 passed in 0.01s ===')"
                ),
                "environment": {"GENERATED_ENV": "generated-value"},
                "pytest": True,
            },
            {"name": "later", "arguments": command("print('generated hidden output')")},
        ],
    )

    result = run_validate(isolated_env)

    assert result.returncode == 0, result.stderr
    assert "pytest: exit 0" in result.stdout
    assert "pytest 3 passed, 0 failed" in result.stdout
    assert "later: exit 0" in result.stdout
    assert "generated hidden output" not in result.stdout
    output = Path(result.stdout.splitlines()[0].removeprefix("Validation output: "))
    try:
        assert output.parent == Path("/tmp")
        assert stat.S_IMODE(output.stat().st_mode) == 0o700
        assert (output / "01-pytest.stdout").read_text(encoding="utf-8").startswith("generated-value\n")
        assert (output / "complete").is_file()
    finally:
        shutil.rmtree(output)


def test_failed_step_prints_full_output_and_later_step_runs(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    output = tmp_path / "validation"
    marker = isolated_env.repo / "later-ran"
    write_validation_profile(
        isolated_env,
        [
            {
                "name": "failure",
                "arguments": command(
                    "import sys; print('complete generated stdout'); "
                    "print('complete generated stderr', file=sys.stderr); raise SystemExit(7)"
                ),
            },
            {
                "name": "later",
                "arguments": command("from pathlib import Path; Path('later-ran').write_text('yes')"),
            },
        ],
    )

    result = run_validate(isolated_env, "--out", output)

    assert result.returncode == 1
    assert marker.read_text(encoding="utf-8") == "yes"
    assert result.stdout.index("failure: exit 7") < result.stdout.index("complete generated stdout")
    assert "complete generated stdout" in result.stdout
    assert "complete generated stderr" in result.stdout
    assert (output / "02-later.stdout").is_file()


def test_always_shown_step_prints_raw_output(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    write_validation_profile(
        isolated_env,
        [
            {
                "name": "shown",
                "arguments": command("print('generated always shown')"),
                "always_show": True,
            }
        ],
    )

    result = run_validate(isolated_env, "--out", tmp_path / "validation")

    assert result.returncode == 0, result.stderr
    assert "shown: exit 0" in result.stdout
    assert "generated always shown" in result.stdout


def test_broken_post_condition_is_a_failure(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    initialized = isolated_env.run(["git", "-C", isolated_env.repo, "init", "-q"])
    assert initialized.returncode == 0, initialized.stderr
    write_validation_profile(
        isolated_env,
        [
            {
                "name": "fix",
                "arguments": command("from pathlib import Path; Path('changed.txt').write_text('changed')"),
                "require_clean": True,
            }
        ],
    )

    result = run_validate(isolated_env, "--out", tmp_path / "validation")

    assert result.returncode == 1
    assert "fix: exit 0" in result.stdout
    assert "post-condition CHANGED" in result.stdout


def test_base_placeholder_is_substituted(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    write_validation_profile(
        isolated_env,
        [
            {
                "name": "base",
                "arguments": command("import sys; print(sys.argv[1])", "{base}..HEAD"),
                "always_show": True,
            }
        ],
    )

    result = run_validate(isolated_env, "--base", "generated-base", "--out", tmp_path / "validation")

    assert result.returncode == 0, result.stderr
    assert "generated-base..HEAD" in result.stdout


def test_missing_base_is_a_usage_error_before_running(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    sentinel = isolated_env.repo / "must-not-run"
    write_validation_profile(
        isolated_env,
        [
            {
                "name": "base",
                "arguments": command("from pathlib import Path; Path('must-not-run').touch()", "{base}"),
            }
        ],
    )
    output = tmp_path / "validation"

    result = run_validate(isolated_env, "--out", output)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.count("\n") == 1
    assert "--base" in result.stderr
    assert not sentinel.exists()
    assert not output.exists()


def test_check_rst_profile_checks_committed_rst_change(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """The check_rst profile passes every committed RST path to its checker."""
    initialized = isolated_env.run(["git", "-C", isolated_env.repo, "init", "-q"])
    assert initialized.returncode == 0, initialized.stderr
    document = isolated_env.repo / "guide.rst"
    document.write_text("Valid\n=====\n", encoding="utf-8")
    for message in ("generated base", "generated defect"):
        if message == "generated defect":
            document.write_text("generated defect\n", encoding="utf-8")
        added = isolated_env.run(["git", "-C", isolated_env.repo, "add", "guide.rst"])
        assert added.returncode == 0, added.stderr
        committed = isolated_env.run(
            [
                "git",
                "-C",
                isolated_env.repo,
                "-c",
                "user.name=Generated",
                "-c",
                "user.email=generated",
                "commit",
                "-q",
                "-m",
                message,
            ]
        )
        assert committed.returncode == 0, committed.stderr
    profile = tomllib.loads((ROOT / "profiles" / "check_rst.toml").read_text(encoding="utf-8"))
    rst_step = next(step for step in profile["validation"] if step["name"] == "check_rst check")
    assert rst_step["arguments"][:4] == ["python3.14", "-m", "check_rst", "check"]
    write_validation_profile(
        isolated_env,
        [
            {
                "name": "check_rst check",
                "arguments": command(
                    "import sys; from pathlib import Path; "
                    "files = [Path(value) for value in sys.argv[1:]]; "
                    "raise SystemExit(any('generated defect' in path.read_text() for path in files))",
                    *rst_step["arguments"][4:],
                ),
                "always_show": True,
            }
        ],
    )

    result = run_validate(
        isolated_env,
        "--base",
        "HEAD^",
        "--out",
        tmp_path / "validation",
    )

    assert result.returncode == 1
    assert "check_rst check: exit 1" in result.stdout


def test_existing_output_directory_is_refused_before_running(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    sentinel = isolated_env.repo / "must-not-run"
    write_validation_profile(
        isolated_env,
        [
            {
                "name": "step",
                "arguments": command("from pathlib import Path; Path('must-not-run').touch()"),
            }
        ],
    )
    output = tmp_path / "existing"
    output.mkdir()

    result = run_validate(isolated_env, "--out", output)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "already exists" in result.stderr
    assert not sentinel.exists()


def test_completion_marker_is_written_last_and_atomically(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    write_validation_profile(
        isolated_env,
        [{"name": "step", "arguments": command("print('generated')")}],
    )
    output = tmp_path / "validation"

    result = run_validate(isolated_env, "--out", output)

    assert result.returncode == 0, result.stderr
    marker = output / "complete"
    assert marker.read_text(encoding="utf-8") == "complete\n"
    assert not (output / ".complete.tmp").exists()
    earlier = [path.stat().st_mtime_ns for path in output.iterdir() if path != marker]
    assert marker.stat().st_mtime_ns >= max(earlier)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["complete"] is True


def test_version_one_profile_remains_valid_and_unknown_key_is_refused(
    isolated_env: IsolatedEnvironment,
) -> None:
    accepted = isolated_env.run([PYTHON, "-I", PROFILE_PROBE, "profile", "unused"])
    assert accepted.returncode == 0, accepted.stderr

    isolated_env.profile.write_text(
        f'profile_version = 1\nname = "generated"\nrepository = "{isolated_env.repo}"\n'
        f'state = "{isolated_env.state}"\nvalidation = []\n',
        encoding="utf-8",
    )
    refused = isolated_env.run([PYTHON, "-I", PROFILE_PROBE, "profile", "unused"])
    assert refused.returncode == 2
    assert "validation" in refused.stderr
    assert "unknown" in refused.stderr
