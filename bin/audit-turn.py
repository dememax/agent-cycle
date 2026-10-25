#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Post-turn audit of escalations and the final JSON result — agent-cycle project
"""Audit one queued turn of the visible Codex thread.

Usage: audit-turn.py THREAD_LOG START_LINE SCHEMA OUT_DIR

Reads the rollout log from START_LINE, and:
- lists every escalated command (sandbox_permissions: require_escalated) and
  flags any that is not `git add` / `git commit` inside the selected
  project's repository (codexlog.CWD);
- saves the turn's final assistant message to OUT_DIR/final-reply.md and,
  if it parses as one JSON object, to OUT_DIR/result.json, then checks the
  schema's required keys, extra keys and enum values.
Exit status (bit flags): 1 escalation outside the allowlist, 2 result
invalid, 4 the turn ended on an error (e.g. usage_limit_exceeded); 0 clean.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codexlog

log, start, schema_path, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
REPO = codexlog.CWD
ALLOW = re.compile(r"^git(\s+-C\s+" + re.escape(REPO) + r"/?)?\s+(add|commit)\b")
# A per-turn extension, decided by the user for one turn only, passed as a
# regular expression in AUDIT_EXTRA_ALLOW (e.g. the prescribed release tag).
import os

EXTRA = re.compile(os.environ["AUDIT_EXTRA_ALLOW"]) if os.environ.get("AUDIT_EXTRA_ALLOW") else None


def allowed(part):
    return bool(ALLOW.match(part) or (EXTRA and EXTRA.fullmatch(part)))


class ParseFailure(ValueError):
    """Source cannot be classified without guessing whether it escalates."""


Token = tuple[str, str, int]
Escalation = tuple[str, str]


def read_string(source: str, start: int, quote: str) -> tuple[str, int]:
    """Read one plain JavaScript string literal."""
    value: list[str] = []
    index = start + 1
    escapes = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "0": "\0"}
    while index < len(source):
        character = source[index]
        if character == quote:
            return "".join(value), index + 1
        if character in "\r\n":
            raise ParseFailure("unterminated string literal")
        if character != "\\":
            value.append(character)
            index += 1
            continue
        index += 1
        if index >= len(source):
            raise ParseFailure("unterminated string literal")
        escaped = source[index]
        if escaped in "\r\n":
            if escaped == "\r" and index + 1 < len(source) and source[index + 1] == "\n":
                index += 1
        elif escaped == "u":
            digits = source[index + 1 : index + 5]
            if len(digits) != 4 or not all(character in "0123456789abcdefABCDEF" for character in digits):
                raise ParseFailure("unrecognized Unicode escape")
            value.append(chr(int(digits, 16)))
            index += 4
        elif escaped == "x":
            digits = source[index + 1 : index + 3]
            if len(digits) != 2 or not all(character in "0123456789abcdefABCDEF" for character in digits):
                raise ParseFailure("unrecognized hexadecimal escape")
            value.append(chr(int(digits, 16)))
            index += 2
        else:
            value.append(escapes.get(escaped, escaped))
        index += 1
    raise ParseFailure("unterminated string literal")


def skip_template(source: str, start: int) -> int:
    """Skip template text, whose contents are data rather than executed calls."""
    index = start + 1
    while index < len(source):
        if source[index] == "`":
            return index + 1
        if source.startswith("${", index):
            raise ParseFailure("template interpolation needs inspection")
        if source[index] == "\\":
            index += 2
        else:
            index += 1
    raise ParseFailure("unterminated template literal")


def tokens(source: str) -> list[Token]:
    """Tokenize enough JavaScript to isolate calls, literals and comments."""
    out: list[Token] = []
    index = 0
    while index < len(source):
        character = source[index]
        if character.isspace():
            index += 1
        elif source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline + 1
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end < 0:
                raise ParseFailure("unterminated block comment")
            index = end + 2
        elif character in "\"'":
            value, end = read_string(source, index, character)
            out.append(("string", value, index))
            index = end
        elif character == "`":
            index = skip_template(source, index)
        elif character.isalpha() or character in "_$":
            end = index + 1
            while end < len(source) and (source[end].isalnum() or source[end] in "_$"):
                end += 1
            out.append(("identifier", source[index:end], index))
            index = end
        elif character.isdigit() or (character == "-" and index + 1 < len(source) and source[index + 1].isdigit()):
            match = re.match(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", source[index:])
            if match is None:
                raise ParseFailure("unrecognized number")
            value = match.group(0)
            out.append(("number", value, index))
            index += len(value)
        else:
            out.append(("symbol", character, index))
            index += 1
    return out


def parse_literal(items: list[Token], index: int) -> tuple[object, int]:
    """Parse JSON-like literal values accepted in an exec_command object."""
    if index >= len(items):
        raise ParseFailure("missing literal value")
    kind, value, _position = items[index]
    if kind == "string":
        return value, index + 1
    if kind == "number":
        return float(value) if any(marker in value for marker in ".eE") else int(value), index + 1
    if kind == "identifier" and value in ("true", "false", "null"):
        return {"true": True, "false": False, "null": None}[value], index + 1
    if value == "{":
        return parse_object(items, index)
    if value == "[":
        result: list[object] = []
        index += 1
        while index < len(items) and items[index][1] != "]":
            item, index = parse_literal(items, index)
            result.append(item)
            if index < len(items) and items[index][1] == ",":
                index += 1
            elif index >= len(items) or items[index][1] != "]":
                raise ParseFailure("unrecognized array literal")
        if index >= len(items):
            raise ParseFailure("unterminated array literal")
        return result, index + 1
    raise ParseFailure("value is not a literal")


def parse_object(items: list[Token], index: int) -> tuple[dict[str, object], int]:
    """Parse a literal object, rejecting computed or duplicate properties."""
    result: dict[str, object] = {}
    index += 1
    while index < len(items) and items[index][1] != "}":
        kind, key, _position = items[index]
        if kind not in ("identifier", "string"):
            raise ParseFailure("object property name is not literal")
        if key in result:
            raise ParseFailure(f"duplicate object property {key}")
        index += 1
        if index >= len(items) or items[index][1] != ":":
            raise ParseFailure(f"object property {key} lacks a colon")
        index += 1
        if key in ("cmd", "workdir", "sandbox_permissions") and (index >= len(items) or items[index][0] != "string"):
            raise ParseFailure(f"{key} value is not a plain string literal")
        result[key], index = parse_literal(items, index)
        if index < len(items) and items[index][1] == ",":
            index += 1
        elif index >= len(items) or items[index][1] != "}":
            raise ParseFailure("unrecognized object literal")
    if index >= len(items):
        raise ParseFailure("unterminated object literal")
    return result, index + 1


def end_of_call(items: list[Token], open_index: int) -> int:
    """Find a call's closing parenthesis so later calls remain visible."""
    depth = 0
    for index in range(open_index, len(items)):
        if items[index][1] == "(":
            depth += 1
        elif items[index][1] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
    return len(items)


def source_escalations(source: str) -> tuple[list[Escalation], list[str]]:
    """Extract executed literal exec_command calls and all ambiguities."""
    try:
        items = tokens(source)
    except ParseFailure as error:
        return [], [str(error)]
    escalations: list[Escalation] = []
    problems: list[str] = []
    index = 0
    while index < len(items):
        kind, value, _position = items[index]
        if kind == "identifier" and value == "exec_command" and index + 1 < len(items) and items[index + 1][1] == "(":
            call_end = end_of_call(items, index + 1)
            argument = index + 2
            if argument >= len(items) or items[argument][1] != "{":
                problems.append("exec_command argument is not a literal object")
                index = call_end
                continue
            try:
                options, after = parse_object(items, argument)
                if after >= len(items) or items[after][1] != ")":
                    raise ParseFailure("exec_command has unrecognized arguments")
                sandbox = options.get("sandbox_permissions")
                if sandbox == "require_escalated":
                    command, workdir = options.get("cmd"), options.get("workdir")
                    if not isinstance(command, str) or not isinstance(workdir, str):
                        raise ParseFailure("escalated exec_command lacks literal cmd or workdir")
                    escalations.append((command, workdir))
            except ParseFailure as error:
                problems.append(str(error))
            index = call_end
            continue
        if kind == "identifier" and value in ("require_escalated", "sandbox_permissions"):
            problems.append(f"{value} occurs outside an exec_command literal object")
        index += 1
    return escalations, problems


def function_escalations(raw: object) -> tuple[list[Escalation], list[str]]:
    """Read a function_call's JSON arguments structurally."""
    try:
        arguments = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as error:
        return [], [f"function_call arguments are not JSON ({error})"]
    if not isinstance(arguments, dict):
        return [], ["function_call arguments are not an object"]
    sandbox = arguments.get("sandbox_permissions")
    if sandbox is None:
        return [], []
    if not isinstance(sandbox, str):
        return [], ["sandbox_permissions value is not a plain string literal"]
    if sandbox != "require_escalated":
        return [], []
    command, workdir = arguments.get("cmd"), arguments.get("workdir")
    if not isinstance(command, str) or not isinstance(workdir, str):
        return [], ["escalated function_call lacks literal cmd or workdir"]
    return [(command, workdir)], []


esc_bad, msgs, reviewer, turn_error = [], [], None, None
for line in open(log, encoding="utf-8").read().splitlines()[start:]:
    e = json.loads(line)
    p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
    if e.get("type") == "turn_context":
        reviewer = p.get("approvals_reviewer")
    if p.get("type") in ("custom_tool_call", "function_call"):
        raw = p.get("arguments") or p.get("input") or ""
        if p.get("type") == "function_call":
            escalations, problems = function_escalations(raw)
        elif isinstance(raw, str):
            escalations, problems = source_escalations(raw)
        else:
            escalations, problems = [], ["custom_tool_call input is not source text"]
        for problem in problems:
            shown = f"needs inspection: {problem}"
            print(f"{e.get('timestamp', '')[11:19]} ESCALATION BAD [] {shown[:180]}")
            esc_bad.append(shown)
        for cmd, workdir in escalations:
            in_repo = workdir.rstrip("/") == REPO
            parts = [x.strip() for x in re.split(r"&&|;|\|\|", cmd) if x.strip()]
            ok = bool(cmd) and all(allowed(x) and (in_repo or f"-C {REPO}" in x) for x in parts)
            print(f"{e.get('timestamp', '')[11:19]} ESCALATION {'ok ' if ok else 'BAD'} [{workdir}] {cmd[:180]}")
            if not ok:
                esc_bad.append(cmd)
    if p.get("type") == "task_complete":
        if p.get("error"):
            err = p["error"]
            turn_error = (err.get("codex_error_info") or "error", err.get("message", ""))
        # One turn only: stop at its own completion, so that a later re-audit
        # never sweeps in the turns that followed.
        break
    if p.get("type") == "message" and p.get("role") == "assistant":
        c = p.get("content") or ""
        if isinstance(c, list):
            c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
        msgs.append(c)
print("approvals_reviewer:", reviewer)
if turn_error:
    # A turn that ended on an error (usage limit, auth, ...) is an incident in
    # its own right, reported before the result check (exit 4).
    print(f"TURN ERROR: {turn_error[0]}: {turn_error[1][:200]}")
final = msgs[-1] if msgs else ""
open(f"{out}/final-reply.md", "w", encoding="utf-8").write(final)
invalid = []
m = re.search(r"\{.*\}", final, re.S)
try:
    r = json.loads(m.group(0)) if m else None
except json.JSONDecodeError as exc:
    r, invalid = None, [f"JSON does not parse: {exc}"]
if r is None and not invalid:
    invalid = ["no JSON object in the final message"]
if r is not None:
    json.dump(r, open(f"{out}/result.json", "w", encoding="utf-8"), indent=2)
    sch = json.load(open(schema_path, encoding="utf-8"))
    invalid += [f"missing {k}" for k in sch["required"] if k not in r]
    invalid += [f"extra {k}" for k in r if k not in sch["properties"]]
    for k, spec in sch["properties"].items():
        if "enum" in spec and k in r and r[k] not in spec["enum"]:
            invalid.append(f"{k}={r[k]!r} not in enum")
print("result:", "valid" if not invalid else "INVALID: " + "; ".join(invalid))
sys.exit((1 if esc_bad else 0) + (2 if invalid else 0) + (4 if turn_error else 0))
