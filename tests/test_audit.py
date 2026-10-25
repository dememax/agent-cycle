# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box characterization of post-turn auditing — agent-cycle project

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from .conftest import PYTHON, ROOT, IsolatedEnvironment
from .rollout import record, task_complete, write_records

if TYPE_CHECKING:
    from pathlib import Path

AUDIT = ROOT / "bin" / "audit-turn.py"
VALID_RESULT = '{"status":"ok"}'


def tool_call(command: str, workdir: str) -> dict[str, object]:
    """Build the nested exec_command shape inspected by the auditor."""
    arguments = (
        'await tools.exec_command({cmd:"'
        + command
        + '",workdir:"'
        + workdir
        + '",sandbox_permissions:"require_escalated"})'
    )
    return record("response_item", {"type": "custom_tool_call", "arguments": arguments})


def tool_input(source: str) -> dict[str, object]:
    """Build one generated custom-tool source input."""
    return record("response_item", {"type": "custom_tool_call", "input": source})


def assistant_message(text: str | list[dict[str, str]]) -> dict[str, object]:
    """Build an assistant response item eligible as the final message."""
    return record("response_item", {"type": "message", "role": "assistant", "content": text})


def write_schema(path: Path) -> None:
    """Write the minimal generated result contract used by audit tests."""
    path.write_text(
        json.dumps(
            {
                "required": ["status"],
                "properties": {"status": {"enum": ["ok"]}},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def run_audit(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    records: list[dict[str, object]],
    *,
    start: int = 0,
    extra_env: dict[str, str] | None = None,
    name: str = "audit",
) -> tuple[int, str, str, Path]:
    """Run the auditor on a generated log and schema."""
    log = tmp_path / f"{name}.jsonl"
    schema = tmp_path / f"{name}-schema.json"
    output = tmp_path / f"{name}-output"
    output.mkdir()
    write_records(log, records)
    write_schema(schema)
    result = isolated_env.run(
        [PYTHON, "-I", AUDIT, log, str(start), schema, output],
        extra_env=extra_env,
    )
    return result.returncode, result.stdout, result.stderr, output


def completed_log(*records: dict[str, object], final: str = VALID_RESULT) -> list[dict[str, object]]:
    """Append a valid final response and completion event."""
    return [*records, assistant_message(final), task_complete("turn-audit")]


@pytest.mark.parametrize(
    ("command", "workdir"),
    [
        ("git add tests/generated.py", "selected"),
        ("git commit -F /tmp/generated-message", "selected"),
        ("git -C selected add tests/generated.py", "elsewhere"),
        ("git -C selected commit -F /tmp/generated-message", "elsewhere"),
    ],
)
def test_allowed_git_escalations_pass(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    command: str,
    workdir: str,
) -> None:
    """Both supported Git forms are accepted for add and commit only."""
    resolved_command = command.replace("selected", str(isolated_env.repo))
    resolved_workdir = str(isolated_env.repo) if workdir == "selected" else str(tmp_path / workdir)

    code, stdout, stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_call(resolved_command, resolved_workdir)),
    )

    assert code == 0, stderr
    assert "ESCALATION ok" in stdout
    assert "result: valid" in stdout


@pytest.mark.parametrize(
    ("command", "workdir"),
    [
        ("git status", "selected"),
        ("git add tests/generated.py", "other"),
        ("git -C other add tests/generated.py", "selected"),
        ("git add tests/generated.py && echo forbidden", "selected"),
    ],
    ids=["other-command", "other-workdir", "other-repository", "compound"],
)
def test_forbidden_escalations_set_bit_one(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    command: str,
    workdir: str,
) -> None:
    """Any command part outside the exact allowlist makes the audit fail."""
    resolved_command = command.replace("other", str(tmp_path / "other"))
    resolved_workdir = str(isolated_env.repo) if workdir == "selected" else str(tmp_path / "other")

    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_call(resolved_command, resolved_workdir)),
    )

    assert code == 1
    assert "ESCALATION BAD" in stdout
    assert "result: valid" in stdout


def test_extra_allow_requires_full_part_match(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """The per-turn extension cannot authorize a command prefix."""
    environment = {"AUDIT_EXTRA_ALLOW": "echo generated-exact"}
    exact = completed_log(tool_call("echo generated-exact", str(isolated_env.repo)))
    code, stdout, stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        exact,
        extra_env=environment,
        name="exact",
    )
    assert code == 0, stderr
    assert "ESCALATION ok" in stdout

    suffix = completed_log(tool_call("echo generated-exact suffix", str(isolated_env.repo)))
    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        suffix,
        extra_env=environment,
        name="suffix",
    )
    assert code == 1
    assert "ESCALATION BAD" in stdout


@pytest.mark.parametrize("final", ['{"status":"wrong"}', None])
def test_invalid_or_absent_result_sets_bit_two(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    final: str | None,
) -> None:
    """A missing or schema-invalid final object is an audit failure."""
    records = [task_complete("turn-audit")] if final is None else completed_log(final=final)

    code, stdout, _stderr, output = run_audit(isolated_env, tmp_path, records)

    assert code == 2
    assert "result: INVALID:" in stdout
    assert (output / "final-reply.md").read_text(encoding="utf-8") == (final or "")
    assert ((output / "result.json").exists()) is (final is not None)


def test_escalation_and_result_bits_combine(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """Independent escalation and result failures produce status three."""
    records = completed_log(tool_call("git status", str(isolated_env.repo)), final='{"status":"wrong"}')

    code, stdout, _stderr, _output = run_audit(isolated_env, tmp_path, records)

    assert code == 3
    assert "ESCALATION BAD" in stdout
    assert "result: INVALID:" in stdout


def test_extracts_last_message_honors_start_line_and_prints_reviewer(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Only the selected turn is audited, and its last assistant message is saved."""
    ignored = tool_call("git status", str(tmp_path / "forbidden"))
    records = [
        ignored,
        record("turn_context", {"approvals_reviewer": "generated-reviewer"}),
        tool_call("git add tests/generated.py", str(isolated_env.repo)),
        assistant_message("draft"),
        assistant_message([{"text": VALID_RESULT}]),
        task_complete("turn-audit"),
    ]

    code, stdout, stderr, output = run_audit(isolated_env, tmp_path, records, start=1)

    assert code == 0, stderr
    assert stdout.count("ESCALATION") == 1
    assert "ESCALATION ok" in stdout
    assert "approvals_reviewer: generated-reviewer" in stdout
    assert (output / "final-reply.md").read_text(encoding="utf-8") == VALID_RESULT
    assert json.loads((output / "result.json").read_text(encoding="utf-8")) == {"status": "ok"}


def test_template_literal_cannot_hide_real_forbidden_escalation(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """An unclosed example inside a template does not absorb an executed call."""
    source = (
        "const patch = `generated fixture: "
        + 'exec_command({cmd:"git add generated",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"`;'
        + "\nawait tools.exec_command("
        + '{cmd:"git push origin main",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"});'
    )

    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 1
    assert "ESCALATION BAD" in stdout
    assert "git push origin main" in stdout
    assert "git add generated" not in stdout


def test_escalation_example_inside_patch_string_is_not_executed(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """A complete escalation-shaped fixture inside a string is ignored."""
    example = (
        'exec_command({cmd:"git push origin main",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"})'
    )
    source = "const patch = " + json.dumps("*** Begin Patch\n+" + example + "\n*** End Patch") + ";"

    code, stdout, stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 0, stderr
    assert "ESCALATION" not in stdout


def test_two_executed_escalations_are_reported_independently(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """An allowed first call cannot conceal a forbidden second call."""
    source = (
        'await tools.exec_command({cmd:"git add generated",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"});'
        + '\nawait tools.exec_command({cmd:"git push origin main",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"});'
    )

    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 1
    assert stdout.count("ESCALATION") == 2
    assert "ESCALATION ok" in stdout
    assert "ESCALATION BAD" in stdout
    assert "git add generated" in stdout
    assert "git push origin main" in stdout


@pytest.mark.parametrize(
    "argument",
    ["options", "JSON.parse(generatedPayload)"],
    ids=["variable", "json-parse"],
)
def test_nonliteral_exec_argument_needs_inspection(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    argument: str,
) -> None:
    """An escalation marker plus a computed argument is always ambiguous."""
    source = (
        'const options = {cmd:"git add generated",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"};\n'
        + f"await tools.exec_command({argument});"
    )

    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 1
    assert "ESCALATION BAD" in stdout
    assert "needs inspection" in stdout


def test_escalation_marker_inside_comment_is_ignored(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Commented example text does not turn a normal call into an escalation."""
    source = (
        '// tools.exec_command({cmd:"git push origin main",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"})\n'
        + 'await tools.exec_command({cmd:"git status",workdir:"'
        + str(isolated_env.repo)
        + '"});'
    )

    code, stdout, stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 0, stderr
    assert "ESCALATION" not in stdout


def test_nonliteral_command_needs_inspection(isolated_env: IsolatedEnvironment, tmp_path: Path) -> None:
    """Even an executed literal object is ambiguous when cmd is computed."""
    source = (
        'await tools.exec_command({cmd:generatedCommand,workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"});'
    )

    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 1
    assert "ESCALATION BAD" in stdout
    assert "needs inspection" in stdout
