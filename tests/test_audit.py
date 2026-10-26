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
IMPLEMENTATION_SCHEMA = ROOT / "schemas" / "implementation-result-v1.json"
REVIEW_SCHEMA = ROOT / "schemas" / "review-result-v1.json"
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


def function_call(arguments: object) -> dict[str, object]:
    """Build a generated function_call with structural JSON arguments."""
    raw = json.dumps(arguments) if not isinstance(arguments, str) else arguments
    return record("response_item", {"type": "function_call", "arguments": raw})


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
    schema_path: Path | None = None,
) -> tuple[int, str, str, Path]:
    """Run the auditor on a generated log and schema."""
    log = tmp_path / f"{name}.jsonl"
    output = tmp_path / f"{name}-output"
    output.mkdir()
    write_records(log, records)
    if schema_path is None:
        schema_path = tmp_path / f"{name}-schema.json"
        write_schema(schema_path)
    result = isolated_env.run(
        [PYTHON, "-I", AUDIT, log, str(start), schema_path, output],
        extra_env=extra_env,
    )
    return result.returncode, result.stdout, result.stderr, output


def completed_log(*records: dict[str, object], final: str = VALID_RESULT) -> list[dict[str, object]]:
    """Append a valid final response and completion event."""
    return [*records, assistant_message(final), task_complete("turn-audit")]


def implementation_result(*, red: object = None) -> dict[str, object]:
    """Build a generated result in the implementation contract's shape."""
    return {
        "schema_version": 1,
        "status": "ready_for_review",
        "work_item": "generated work item",
        "plan_revision": 4,
        "base_commit": "generated-base",
        "commits": [{"role": "single", "sha": "generated-sha", "subject": "generated subject"}],
        "red": red,
        "behaviour": "changed",
        "red_tests_modified_by_green": False,
        "validation_claimed": ["generated validation"],
        "blocked_reason": None,
        "report": "generated report",
    }


def review_result() -> dict[str, object]:
    """Build a generated result in the review contract's shape."""
    return {
        "schema_version": 1,
        "verdict": "approved",
        "reviewed": "generated review",
        "findings": [
            {
                "id": "GENERATED-1",
                "severity": "note",
                "summary": "generated summary",
                "evidence": "generated evidence",
            }
        ],
        "decisions_requested": [],
        "report": "generated report",
    }


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


@pytest.mark.parametrize(
    "final",
    [
        "generated prose\n" + VALID_RESULT,
        VALID_RESULT + "\ngenerated prose",
        "```json\n" + VALID_RESULT + "\n```",
        VALID_RESULT + "\n" + VALID_RESULT,
    ],
    ids=["prose-before", "prose-after", "fence", "two-objects"],
)
def test_result_must_be_exactly_one_json_object(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    final: str,
) -> None:
    """Only surrounding whitespace may accompany the final JSON object."""
    code, stdout, _stderr, output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(final=final),
    )

    assert code == 2
    assert "result: INVALID:" in stdout
    assert (output / "final-reply.md").read_text(encoding="utf-8") == final
    assert not (output / "result.json").exists()


@pytest.mark.parametrize(
    ("final", "schema_path"),
    [
        ('{"status":"wrong","status":"ok"}', None),
        (
            json.dumps(review_result()).replace(
                '"severity": "note"',
                '"severity": "wrong", "severity": "note"',
            ),
            REVIEW_SCHEMA,
        ),
    ],
    ids=["top-level", "nested"],
)
def test_result_rejects_duplicate_keys(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    final: str,
    schema_path: Path | None,
) -> None:
    """Duplicate object members cannot be hidden by JSON's last-value behavior."""
    code, stdout, _stderr, output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(final=final),
        schema_path=schema_path,
    )

    assert code == 2
    assert "result: INVALID:" in stdout
    assert "duplicate" in stdout
    assert not (output / "result.json").exists()


def test_result_rejects_non_finite_number(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Python's non-standard NaN JSON extension is not part of the contract."""
    final = json.dumps(implementation_result()).replace('"generated report"', "NaN")

    code, stdout, _stderr, output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(final=final),
        schema_path=IMPLEMENTATION_SCHEMA,
    )

    assert code == 2
    assert "result: INVALID:" in stdout
    assert "NaN" in stdout
    assert not (output / "result.json").exists()


@pytest.mark.parametrize(
    ("change", "path"),
    [
        ({"plan_revision": "four"}, "plan_revision"),
        ({"commits": [7]}, "commits[0]"),
        (
            {
                "red": {
                    "runner": "pytest",
                    "selectors": [],
                    "expected_failing": [],
                }
            },
            "red.failure_kind",
        ),
        ({"red": "not an object"}, "red"),
        ({"plan_revision": True}, "plan_revision"),
    ],
    ids=["top-level", "array-item", "missing-nested-key", "any-of-type", "bool-is-not-integer"],
)
def test_result_validates_types_and_required_fields_recursively(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    change: dict[str, object],
    path: str,
) -> None:
    """Types, array items and required properties are enforced at every depth."""
    final_result = implementation_result()
    final_result.update(change)

    code, stdout, _stderr, output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(final=json.dumps(final_result)),
        schema_path=IMPLEMENTATION_SCHEMA,
    )

    assert code == 2
    assert "result: INVALID:" in stdout
    assert path in stdout
    assert (output / "result.json").exists()


def test_result_validates_nested_enum_and_additional_properties(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Nested enum and object-boundary errors share the result's single line."""
    final_result = review_result()
    findings = final_result["findings"]
    assert isinstance(findings, list)
    finding = findings[0]
    assert isinstance(finding, dict)
    finding["severity"] = "generated-invalid"
    finding["generated_extra"] = True

    code, stdout, _stderr, output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(final=json.dumps(final_result)),
        schema_path=REVIEW_SCHEMA,
    )

    result_line = next(line for line in stdout.splitlines() if line.startswith("result:"))
    assert code == 2
    assert "findings[0].severity" in result_line
    assert "findings[0].generated_extra" in result_line
    assert "; " in result_line
    assert (output / "result.json").exists()


def test_result_refuses_an_unsupported_schema_keyword(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """A schema extension cannot silently weaken the audit's validation."""
    schema = tmp_path / "unsupported-schema.json"
    schema.write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["status"],
                "properties": {
                    "status": {"type": "string", "minimum": 1},
                },
                "additionalProperties": False,
            }
        ),
        encoding="utf-8",
    )

    code, stdout, _stderr, output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(),
        schema_path=schema,
    )

    assert code == 2
    assert "result: INVALID:" in stdout
    assert "minimum" in stdout
    assert "properties.status" in stdout
    assert (output / "result.json").exists()


@pytest.mark.parametrize(
    ("schema_path", "final_result"),
    [
        (IMPLEMENTATION_SCHEMA, implementation_result()),
        (
            IMPLEMENTATION_SCHEMA,
            implementation_result(
                red={
                    "runner": "pytest",
                    "selectors": ["tests/test_generated.py::test_generated"],
                    "expected_failing": ["tests/test_generated.py::test_generated"],
                    "failure_kind": "exception",
                }
            ),
        ),
        (REVIEW_SCHEMA, review_result()),
    ],
    ids=["implementation-red-null", "implementation-red-exception", "review"],
)
def test_shipped_schemas_accept_valid_results(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    schema_path: Path,
    final_result: dict[str, object],
) -> None:
    """Both shipped recursive contracts accept their complete valid shapes."""
    final = " \n" + json.dumps(final_result) + "\n\t"

    code, stdout, stderr, output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(final=final),
        schema_path=schema_path,
    )

    assert code == 0, stderr
    assert "result: valid" in stdout
    assert json.loads((output / "result.json").read_text(encoding="utf-8")) == final_result


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


@pytest.mark.parametrize(
    ("property_name", "value"),
    [("workdir", "generatedWorkdir"), ("sandbox_permissions", "generatedPermission")],
)
def test_other_nonliteral_escalation_properties_need_inspection(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    property_name: str,
    value: str,
) -> None:
    """Workdir and permission are subject to the same literal-only rule as cmd."""
    properties = {
        "cmd": '"git add generated"',
        "workdir": f'"{isolated_env.repo}"',
        "sandbox_permissions": '"require_escalated"',
    }
    properties[property_name] = value
    source = "await tools.exec_command({" + ",".join(f"{key}:{item}" for key, item in properties.items()) + "});"

    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 1
    assert "ESCALATION BAD" in stdout
    assert f"{property_name} value is not a plain string literal" in stdout
    assert "needs inspection" in stdout


@pytest.mark.parametrize(
    "source",
    [
        "const require_escalated = generatedPermission;",
        'await tools.exec_command({...generatedOptions,sandbox_permissions:"require_escalated"});',
    ],
    ids=["bare-marker", "unrecognized-object"],
)
def test_other_ambiguous_source_needs_inspection(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    source: str,
) -> None:
    """In-scope markers and unrecognized object syntax fail closed."""
    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 1
    assert "ESCALATION BAD" in stdout
    assert "needs inspection" in stdout


@pytest.mark.parametrize(
    "source",
    ['const generated = "unterminated', "const generated = `${computedValue}`;"],
    ids=["unterminated-string", "template-interpolation"],
)
def test_ambiguous_source_without_escalation_marker_is_out_of_scope(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    source: str,
) -> None:
    """Source without a literal escalation marker needs no inspection."""
    code, stdout, stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 0, stderr
    assert "ESCALATION" not in stdout


def test_function_call_arguments_are_handled_structurally(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """JSON function-call arguments retain independent allowlist decisions."""
    common = {"workdir": str(isolated_env.repo), "sandbox_permissions": "require_escalated"}
    records = completed_log(
        function_call(common | {"cmd": "git add generated"}),
        function_call(common | {"cmd": "git push origin main"}),
    )

    code, stdout, _stderr, _output = run_audit(isolated_env, tmp_path, records)

    assert code == 1
    assert stdout.count("ESCALATION") == 2
    assert "ESCALATION ok" in stdout
    assert "ESCALATION BAD" in stdout
    assert "git push origin main" in stdout


def test_malformed_function_call_arguments_need_inspection(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """A function call that is not valid JSON cannot be silently ignored."""
    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(function_call("{not JSON")),
    )

    assert code == 1
    assert "ESCALATION BAD" in stdout
    assert "function_call arguments are not JSON" in stdout
    assert "needs inspection" in stdout


@pytest.mark.parametrize("pattern", ["`", '"'], ids=["backtick", "quote"])
def test_regex_literal_does_not_hide_real_escalation(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    pattern: str,
) -> None:
    """Regex contents cannot be mistaken for string or template delimiters."""
    regex = f"/{pattern}/g"
    source = (
        f'const before = generated.replace({regex}, "");\n'
        + 'await tools.exec_command({cmd:"git push origin main",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"});\n'
        + f'const after = generated.replace({regex}, "");'
    )

    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 1
    assert "ESCALATION BAD" in stdout
    assert "git push origin main" in stdout


def test_division_next_to_real_escalation_is_not_a_regex(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """A slash after an identifier retains division semantics."""
    source = (
        "const ratio = numerator / denominator;\n"
        + 'await tools.exec_command({cmd:"git push origin main",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"});'
    )

    code, stdout, _stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 1
    assert "git push origin main" in stdout


def test_non_escalated_loop_with_interpolation_is_out_of_scope(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Ordinary computed commands do not require escalation inspection."""
    source = (
        "for (const generatedCommand of commands) {\n"
        "  const label = `running ${generatedCommand}`;\n"
        + '  await tools.exec_command({cmd:generatedCommand,workdir:"'
        + str(isolated_env.repo)
        + '"});\n}'
    )

    code, stdout, stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 0, stderr
    assert "ESCALATION" not in stdout


def test_escalated_template_command_with_interpolation_needs_inspection(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """An escalated cmd must remain a plain string rather than a template."""
    source = (
        'await tools.exec_command({cmd:`git ${generatedAction}`,workdir:"'
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


def test_unrelated_interpolation_in_scoped_source_is_parsed(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Executed interpolation away from the call does not make a literal escalation ambiguous."""
    source = (
        "const label = `generated ${name.toUpperCase()}`;\n"
        + 'await tools.exec_command({cmd:"git add generated",workdir:"'
        + str(isolated_env.repo)
        + '",sandbox_permissions:"require_escalated"});'
    )

    code, stdout, stderr, _output = run_audit(
        isolated_env,
        tmp_path,
        completed_log(tool_input(source)),
    )

    assert code == 0, stderr
    assert "ESCALATION ok" in stdout
    assert "ESCALATION BAD" not in stdout
