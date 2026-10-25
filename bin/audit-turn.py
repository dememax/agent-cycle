#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Post-turn audit of escalations and the final JSON result — agent-cycle project
"""Audit one queued turn of the visible Codex thread.

Usage: audit-turn.py THREAD_LOG START_LINE SCHEMA OUT_DIR

Reads the rollout log from START_LINE, and:
- lists every escalated command (sandbox_permissions: require_escalated) and
  flags any that is not `git add` / `git commit` inside ~/github/check_rst;
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

log, start, schema_path, out = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
REPO = str(Path.home() / "github" / "check_rst")
ALLOW = re.compile(r"^git(\s+-C\s+" + re.escape(REPO) + r"/?)?\s+(add|commit)\b")
# A per-turn extension, decided by the user for one turn only, passed as a
# regular expression in AUDIT_EXTRA_ALLOW (e.g. the prescribed release tag).
import os

EXTRA = re.compile(os.environ["AUDIT_EXTRA_ALLOW"]) if os.environ.get("AUDIT_EXTRA_ALLOW") else None


def allowed(part):
    return bool(ALLOW.match(part) or (EXTRA and EXTRA.fullmatch(part)))


esc_bad, msgs, reviewer, turn_error = [], [], None, None
for line in open(log, encoding="utf-8").read().splitlines()[start:]:
    e = json.loads(line)
    p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
    if e.get("type") == "turn_context":
        reviewer = p.get("approvals_reviewer")
    if p.get("type") in ("custom_tool_call", "function_call"):
        raw = p.get("arguments") or p.get("input") or ""
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            args = {"raw": raw}
        blob = raw if isinstance(raw, str) else json.dumps(raw)
        if "require_escalated" in blob:
            # Each escalated call is an exec_command({...}) inside a small JS
            # snippet; take cmd and workdir from it. Unparseable means BAD.
            calls = re.findall(r"exec_command\(\{(.*?)\}\)", blob, re.S) or [blob]
            for call in calls:
                if "require_escalated" not in call:
                    continue
                # Keys appear unquoted (cmd:) or quoted ("workdir":); accept both.
                cm = re.search(r"\"?cmd\"?:\s*(\"((?:[^\"\\]|\\.)*)\"|`([^`]*)`)", call, re.S)
                wd = re.search(r"\"?workdir\"?:\s*\"((?:[^\"\\]|\\.)*)\"", call)
                cmd = cm.group(2) if cm and cm.group(2) is not None else (cm.group(3) if cm else None)
                workdir = wd.group(1) if wd else ""
                in_repo = workdir.rstrip("/") == REPO
                parts = [x.strip() for x in re.split(r"&&|;|\|\|", cmd or "") if x.strip()]
                ok = bool(cmd) and all(allowed(x) and (in_repo or f"-C {REPO}" in x) for x in parts)
                shown = cmd if cmd else call.strip()[:120]
                print(f"{e.get('timestamp', '')[11:19]} ESCALATION {'ok ' if ok else 'BAD'} [{workdir}] {shown[:180]}")
                if not ok:
                    esc_bad.append(shown)
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
