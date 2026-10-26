#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Fail-closed identification of a new visible Codex thread — agent-cycle project
"""Identify a new visible Codex thread, fail-closed, and record it as active.

Usage: codex-identify-thread.py SENTINEL SINCE_ISO OLD_THREAD_LOG [--write]

SINCE_ISO must carry a time-zone offset (for example 2026-10-25T11:40:00+01:00).

A candidate is a rollout file under ~/.codex/sessions that parses
completely (codexlog.records), whose session_meta says source "vscode",
originator "codex_vscode", cwd the project's repository (codexlog.REPO_DIR), created after
SINCE_ISO, and whose INITIAL composer message (the first "user.text" item)
equals SENTINEL apart from trailing newlines (codexlog.canonical), in a completed initial turn. Exactly one candidate
must exist. Unparseable files are reported and count as a failure when
they otherwise look like candidates (same source, originator and cwd).

It compares the candidate's first turn_context with the old thread's last
one on codexlog.STOPPING_KEYS, and prints DIAGNOSTIC_KEYS. When the old
thread belongs to another repository (the first chat of a project), its
settings are compared relocated: every string that is the old repository's
path, or a path under it, is moved to the selected repository first. With --write and
no stopping difference, it writes active-codex-thread.json in the project's
state directory (codexlog.STATE_DIR).

The project is selected by AGENT_CYCLE_REPO and AGENT_CYCLE_STATE, both
check_rst's when unset (codexlog).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codexlog

ACTIVE = codexlog.STATE_DIR / "active-codex-thread.json"


def relocate(value: object, old_root: str, new_root: str) -> object:
    """VALUE with each string that is OLD_ROOT, or a path under it, moved to NEW_ROOT."""
    if isinstance(value, str):
        if value == old_root or value.startswith(old_root + "/"):
            return new_root + value[len(old_root) :]
        return value
    if isinstance(value, list):
        return [relocate(item, old_root, new_root) for item in value]
    if isinstance(value, dict):
        return {key: relocate(item, old_root, new_root) for key, item in value.items()}
    return value


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    sentinel, since_iso, old_log = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    write = "--write" in sys.argv[4:]
    since = datetime.fromisoformat(since_iso)
    if since.tzinfo is None:
        print("FAIL: SINCE_ISO needs a time-zone offset")
        return 2
    candidates = []
    damaged = []
    for path in sorted((Path.home() / ".codex/sessions").rglob("rollout-*.jsonl")):
        if path.resolve() == old_log.resolve():
            continue
        try:
            first = json.loads(path.open(encoding="utf-8").readline())
            meta = first.get("payload") or {}
        except (OSError, ValueError) as error:
            # Unreadable metadata: ambiguous if the file is newer than SINCE.
            try:
                newer = datetime.fromtimestamp(path.stat().st_mtime).astimezone() > since
            except OSError:
                newer = True
            if newer:
                damaged.append((path, f"unreadable session_meta ({error})"))
            continue
        if first.get("type") != "session_meta":
            try:
                newer = datetime.fromtimestamp(path.stat().st_mtime).astimezone() > since
            except OSError:
                newer = True
            if newer:
                damaged.append((path, "first record is not session_meta"))
            continue
        if (meta.get("source"), meta.get("originator"), meta.get("cwd")) != ("vscode", "codex_vscode", codexlog.CWD):
            continue
        created = datetime.fromisoformat(meta["timestamp"].replace("Z", "+00:00"))
        if created <= since:
            continue
        try:
            recs = codexlog.records(path)
            _turn, text = codexlog.initial_composer(recs)
        except codexlog.LogError as error:
            damaged.append((path, str(error)))
            continue
        if codexlog.canonical(text) == codexlog.canonical(sentinel):
            candidates.append((path, meta, recs))
    print(f"candidates: {len(candidates)}; unreadable look-alikes: {len(damaged)}")
    for path, meta, _recs in candidates:
        print(f"  {meta['id']}  {meta['timestamp']}  {path}")
    for path, problem in damaged:
        print(f"  UNREADABLE {path}: {problem}")
    if len(candidates) != 1 or damaged:
        print("FAIL: exactly one readable candidate, and no unreadable look-alike, is required")
        return 1
    path, meta, recs = candidates[0]
    try:
        old_recs = codexlog.records(old_log)
    except codexlog.LogError as error:
        print(f"FAIL: old log: {error}")
        return 1
    new_contexts, old_contexts = codexlog.turn_contexts(recs), codexlog.turn_contexts(old_recs)
    if not new_contexts or not old_contexts:
        print("FAIL: missing turn_context")
        return 1
    new, old = new_contexts[0], old_contexts[-1]
    # A first chat for another project takes its settings from a chat of
    # another repository: compare them relocated to the selected one.
    old_cwd = codexlog.session_meta(old_recs).get("cwd")
    if isinstance(old_cwd, str) and old_cwd != codexlog.CWD:
        print(f"  profile compared relocated: {old_cwd} -> {codexlog.CWD}")
        old = {k: relocate(v, old_cwd, codexlog.CWD) for k, v in old.items()}
    stopping = [k for k in codexlog.STOPPING_KEYS if new.get(k) != old.get(k)]
    for key in codexlog.STOPPING_KEYS:
        print(f"  {'DIFF' if key in stopping else 'same'} {key}: {json.dumps(new.get(key))[:160]}")
    for key in codexlog.DIAGNOSTIC_KEYS:
        print(
            f"  {'same' if new.get(key) == old.get(key) else 'diff (diagnostic)'} {key}: {json.dumps(new.get(key))[:160]}"
        )
    if stopping:
        print("FAIL: behavioural profile differs from the old thread: " + ", ".join(stopping))
        return 1
    if write:
        ACTIVE.write_text(
            json.dumps(
                {
                    "thread_id": meta["id"],
                    "log_path": str(path),
                    "source": meta.get("source"),
                    "originator": meta.get("originator"),
                    "cwd": meta.get("cwd"),
                    "created": meta["timestamp"],
                    "sentinel": sentinel,
                    "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "replaces_thread_log": str(old_log),
                    "profile_baseline": {k: new.get(k) for k in codexlog.STOPPING_KEYS},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"written: {ACTIVE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
