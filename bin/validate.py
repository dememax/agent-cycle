#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Ordered project validation runner — agent-cycle project
"""Run the validation steps declared by the selected project profile.

Usage: validate.py [--base REV] [--out DIR]
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codexlog import ProfileError, ValidationStep, load_project_profile

PYTEST_COUNT = re.compile(r"(?P<count>[0-9]+) (?P<kind>failed|passed)\b")
SAFE_NAME = re.compile(r"[^a-z0-9]+")


class UsageError(Exception):
    """Arguments or profile settings prevent any validation from starting."""


@dataclass(frozen=True)
class Options:
    """Validated command-line options."""

    base: str | None
    output: Path | None


@dataclass(frozen=True)
class StepResult:
    """One completed step and the paths holding its unabridged output."""

    step: ValidationStep
    arguments: tuple[str, ...]
    exit_status: int
    seconds: float
    post_condition: str
    stdout_path: Path
    stderr_path: Path
    pytest_passed: int | None
    pytest_failed: int | None

    @property
    def failed(self) -> bool:
        """Whether the command or its requested post-condition failed."""
        return self.exit_status != 0 or self.post_condition not in ("not requested", "unchanged")

    def summary(self) -> dict[str, Any]:
        """Return the stable JSON representation of this step."""
        result: dict[str, Any] = {
            "name": self.step.name,
            "arguments": self.arguments,
            "exit_status": self.exit_status,
            "seconds": round(self.seconds, 3),
            "post_condition": self.post_condition,
            "stdout": self.stdout_path.name,
            "stderr": self.stderr_path.name,
            "always_show": self.step.always_show,
        }
        if self.step.pytest:
            result["pytest"] = {"passed": self.pytest_passed, "failed": self.pytest_failed}
        return result


def parse_options(arguments: list[str]) -> Options:
    """Parse the intentionally small command line without permissive aliases."""
    base = None
    output = None
    index = 0
    while index < len(arguments):
        option = arguments[index]
        if option not in ("--base", "--out"):
            raise UsageError(f"unknown argument {option!r}; usage: validate.py [--base REV] [--out DIR]")
        if index + 1 >= len(arguments):
            raise UsageError(f"{option}: missing value")
        value = arguments[index + 1]
        if not value:
            raise UsageError(f"{option}: value must not be empty")
        if option == "--base":
            if base is not None:
                raise UsageError("--base: specified more than once")
            base = value
        else:
            if output is not None:
                raise UsageError("--out: specified more than once")
            output = Path(value)
        index += 2
    return Options(base, output)


def expand_arguments(step: ValidationStep, base: str | None) -> tuple[str, ...]:
    """Substitute the base revision and expand a leading portable home spelling."""
    if any("{base}" in argument for argument in step.arguments) and base is None:
        raise UsageError(f"validation step {step.name!r} uses {{base}} but --base was not provided")
    home = os.environ.get("HOME")
    expanded = []
    for argument in step.arguments:
        value = argument.replace("{base}", base or "")
        if value.startswith("~/"):
            if not home or not Path(home).is_absolute():
                raise UsageError(f"validation step {step.name!r}: cannot expand ~/ because HOME is not absolute")
            value = str(Path(home) / value[2:])
        expanded.append(value)
    return tuple(expanded)


def create_output(path: Path | None) -> Path:
    """Create a private fresh output directory, refusing every existing target."""
    try:
        if path is None:
            return Path(tempfile.mkdtemp(prefix="agent-cycle-validation-", dir="/tmp"))
        path.mkdir(mode=0o700)
        return path
    except FileExistsError:
        raise UsageError(f"--out: {path}: already exists") from None
    except OSError as error:
        label = "default output directory" if path is None else f"--out: {path}"
        raise UsageError(f"{label}: cannot create ({error})") from None


def git_status(repository: Path) -> tuple[bytes | None, str | None]:
    """Read the exact worktree state used by a require-clean post-condition."""
    try:
        result = subprocess.run(
            ["git", "--no-optional-locks", "status", "--porcelain=v1", "-uall"],
            cwd=repository,
            capture_output=True,
            check=False,
        )
    except OSError as error:
        return None, str(error)
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip()
        return None, message or f"git status exited {result.returncode}"
    return result.stdout, None


def pytest_counts(stdout: bytes, stderr: bytes) -> tuple[int | None, int | None]:
    """Extract pass/fail counts from pytest's final non-empty output line."""
    lines = (stdout + stderr).decode(errors="replace").splitlines()
    final = next((line for line in reversed(lines) if line.strip()), "")
    counts = {"passed": 0, "failed": 0}
    found = False
    for match in PYTEST_COUNT.finditer(final):
        counts[match.group("kind")] = int(match.group("count"))
        found = True
    return (counts["passed"], counts["failed"]) if found else (None, None)


def output_paths(output: Path, index: int, name: str) -> tuple[Path, Path]:
    """Make stable, unique raw-output names from a display name."""
    slug = SAFE_NAME.sub("-", name.lower()).strip("-") or "step"
    stem = f"{index:02d}-{slug}"
    return output / f"{stem}.stdout", output / f"{stem}.stderr"


def run_step(
    repository: Path,
    output: Path,
    index: int,
    step: ValidationStep,
    arguments: tuple[str, ...],
) -> StepResult:
    """Run one step and preserve its output even when execution itself fails."""
    before, before_error = git_status(repository) if step.require_clean else (None, None)
    environment = dict(os.environ)
    environment.update(step.environment)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            arguments,
            cwd=repository,
            env=environment,
            capture_output=True,
            check=False,
        )
        exit_status = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except OSError as error:
        exit_status = 127
        stdout = b""
        stderr = f"validate: cannot run {arguments[0]!r} ({error})\n".encode()
    seconds = time.monotonic() - started

    post_condition = "not requested"
    if step.require_clean:
        after, after_error = git_status(repository)
        if before_error is not None or after_error is not None:
            post_condition = "ERROR"
            details = "; ".join(message for message in (before_error, after_error) if message is not None)
            stderr += f"validate: cannot check worktree post-condition ({details})\n".encode()
        else:
            post_condition = "unchanged" if before == after else "CHANGED"

    stdout_path, stderr_path = output_paths(output, index, step.name)
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    passed, failed = pytest_counts(stdout, stderr) if step.pytest else (None, None)
    return StepResult(
        step,
        arguments,
        exit_status,
        seconds,
        post_condition,
        stdout_path,
        stderr_path,
        passed,
        failed,
    )


def render(results: list[StepResult], output: Path) -> bytes:
    """Render the compact summary followed by every required raw byte stream."""
    lines = [f"Validation output: {output}"]
    for result in results:
        line = (
            f"- {result.step.name}: exit {result.exit_status}; {result.seconds:.3f}s; "
            f"post-condition {result.post_condition}"
        )
        if result.step.pytest:
            passed = "unknown" if result.pytest_passed is None else str(result.pytest_passed)
            failed = "unknown" if result.pytest_failed is None else str(result.pytest_failed)
            line += f"; pytest {passed} passed, {failed} failed"
        lines.append(line)
    rendered = ("\n".join(lines) + "\n").encode()
    for result in results:
        if not (result.failed or result.step.always_show):
            continue
        for label, path in (("stdout", result.stdout_path), ("stderr", result.stderr_path)):
            content = path.read_bytes()
            rendered += f"--- {result.step.name} {label} ---\n".encode() + content
            if not content.endswith(b"\n"):
                rendered += b"\n"
    return rendered


def write_completion(output: Path, results: list[StepResult]) -> None:
    """Write the machine summary, then publish the completion marker atomically."""
    summary = {
        "complete": True,
        "successful": not any(result.failed for result in results),
        "steps": [result.summary() for result in results],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    temporary = output / ".complete.tmp"
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write("complete\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(output / "complete")


def main(arguments: list[str]) -> int:
    """Validate the selected project and report all step outcomes."""
    try:
        options = parse_options(arguments)
        profile = load_project_profile()
        if not profile.validation:
            raise UsageError("selected profile declares no validation steps")
        if not profile.repository.is_dir():
            raise UsageError(f"profile repository is not a directory: {profile.repository}")
        commands = [(step, expand_arguments(step, options.base)) for step in profile.validation]
        if options.output is not None and options.output.exists():
            raise UsageError(f"--out: {options.output}: already exists")
        output = create_output(options.output)
    except (ProfileError, UsageError) as error:
        print(f"validate: {error}", file=sys.stderr)
        return 2

    results = [
        run_step(profile.repository, output, index, step, command) for index, (step, command) in enumerate(commands, 1)
    ]
    write_completion(output, results)
    sys.stdout.buffer.write(render(results, output))
    return 1 if any(result.failed for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
