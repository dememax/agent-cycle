#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Fail-closed queueing of one turn into the active Codex thread — agent-cycle project
"""Queue one S0 turn into the ACTIVE visible Codex thread, fail-closed.

Usage: codex-queue-turn.py TURN_DIR

Holds an exclusive lock (queue.lock) from the checks until Codex has
visibly started the new turn, so two drivers cannot both queue. Refuses
(exit 1) unless all of these hold:
- active-codex-thread.json exists; its log parses completely;
- the record's cwd is the selected project's repository (codexlog.CWD);
- the log's session_meta id, source, originator, cwd and timestamp equal
  the record's;
- the log's initial composer message is exactly the recorded sentinel, in a
  completed turn;
- no turn is running (every task_started has a later task_complete with
  the same turn_id);
- no earlier submission is pending (pending.json from a queue whose turn
  never started);
- the latest turn_context equals the recorded profile_baseline on every
  stopping key. A setting changed in the panel after the last turn cannot
  be seen until a turn records it; the post-turn audit rechecks it;
- TURN_DIR/prompt.md starts with "[S0 DRIVER: Claude Code]".

Before submitting it writes pending.json atomically and fsyncs it and its
directory. After submitting it polls the log with the strict reader until
exactly one new turn appears whose composer message equals prompt.md
(codexlog.canonical); a second new turn, a foreign prompt, a malformed log
line or a timeout (300 s) refuses and keeps pending.json. On success it
writes thread-log-path, thread-log-lines-before, started, stdout.txt and
turn-id into TURN_DIR, removes pending.json and fsyncs the directory.
"""

from __future__ import annotations

import fcntl
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codexlog

# S0_STATE_DIR, the older name, still overrides the selected project's state directory.
STATE = Path(os.environ["S0_STATE_DIR"]) if os.environ.get("S0_STATE_DIR") else codexlog.STATE_DIR
ACTIVE = STATE / "active-codex-thread.json"
LOCK = STATE / "queue.lock"
PENDING = STATE / "pending.json"


def refuse(message: str) -> int:
    print(f"codex-queue-turn: REFUSED: {message}", file=sys.stderr)
    return 1


def codex_binary() -> str | None:
    if os.environ.get("CODEX"):
        return os.environ["CODEX"]
    found = sorted(glob.glob(str(Path.home() / ".vscode/extensions/openai.chatgpt-*/bin/linux-x86_64/codex")))
    return found[-1] if found else None


def fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_durably(path: Path, text: str) -> None:
    """Write atomically and fsync the file and its directory before returning."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fsync_dir(path.parent)


def check(active: dict, prompt_text: str | None) -> tuple[list[dict] | None, str | None]:
    if active.get("cwd") != codexlog.CWD:
        return None, f"active record's cwd {active.get('cwd')!r} is not the selected repository {codexlog.CWD!r}"
    log = Path(active["log_path"])
    try:
        recs = codexlog.records(log)
        meta = codexlog.session_meta(recs)
        for key, field in (
            ("thread_id", "id"),
            ("source", "source"),
            ("originator", "originator"),
            ("cwd", "cwd"),
            ("created", "timestamp"),
        ):
            if key not in active:
                return None, f"active record lacks {key}"
            if meta.get(field) != active[key]:
                return None, f"session_meta {field} {meta.get(field)!r} != recorded {active[key]!r}"
        _turn, text = codexlog.initial_composer(recs)
        if codexlog.canonical(text) != codexlog.canonical(active["sentinel"]):
            return None, "the initial composer message is not the recorded sentinel"
        running = codexlog.running_turns(recs)
        if running:
            return None, f"turn running: {running}"
        contexts = codexlog.turn_contexts(recs)
        if not contexts:
            return None, "no turn_context"
        latest = contexts[-1]
        drift = [k for k in codexlog.STOPPING_KEYS if latest.get(k) != active["profile_baseline"].get(k)]
        if drift:
            return None, "profile drift on: " + ", ".join(drift)
    except (codexlog.LogError, OSError, KeyError) as error:
        return None, f"log check failed: {error}"
    if prompt_text is None:
        return None, "no prompt.md"
    if not prompt_text.startswith("[S0 DRIVER: Claude Code]"):
        return None, "prompt.md lacks the driver header"
    return recs, None


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    turn_dir = Path(sys.argv[1])
    if not ACTIVE.is_file():
        return refuse("no active-codex-thread.json")
    codex = codex_binary()
    if not codex or not os.access(codex, os.X_OK):
        return refuse("codex binary not found")
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return refuse("another queue is in progress (queue.lock held)")
        active = json.loads(ACTIVE.read_text(encoding="utf-8"))
        if PENDING.exists():
            pending = json.loads(PENDING.read_text(encoding="utf-8"))
            return refuse(f"an earlier submission never started a turn: {pending}; investigate, then remove {PENDING}")
        # Read the prompt once, under the lock; the same text is validated,
        # submitted and compared, so a later change to the file cannot slip in.
        prompt_file = turn_dir / "prompt.md"
        prompt_text = prompt_file.read_text(encoding="utf-8") if prompt_file.is_file() else None
        recs, problem = check(active, prompt_text)
        if problem:
            return refuse(problem)
        log = Path(active["log_path"])
        before = len(recs)
        known = set(codexlog.turn_states(recs))
        (turn_dir / "thread-log-path").write_text(f"{log}\n", encoding="utf-8")
        (turn_dir / "thread-log-lines-before").write_text(f"{before}\n", encoding="utf-8")
        (turn_dir / "started").write_text(
            datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z") + "\n", encoding="utf-8"
        )
        write_durably(
            PENDING,
            json.dumps({"turn_dir": str(turn_dir), "thread_id": active["thread_id"], "lines_before": before}) + "\n",
        )
        timeout = float(os.environ.get("S0_QUEUE_TIMEOUT", "300"))
        try:
            result = subprocess.run(
                [codex, "queue", "--thread", active["thread_id"], "--message", prompt_text],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return refuse(f"codex queue did not return within {timeout:g} s; pending.json kept")
        (turn_dir / "stdout.txt").write_text(
            f"{result.stdout}queue_exit={result.returncode} thread={active['thread_id']}\n", encoding="utf-8"
        )
        (turn_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
        if result.returncode != 0:
            return refuse(f"codex queue failed (exit {result.returncode}); pending.json kept")
        prompt = codexlog.canonical(prompt_text)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(3)
            try:
                recs = codexlog.records(log)
            except codexlog.IncompleteLastLine:
                continue
            except (codexlog.LogError, OSError) as error:
                return refuse(f"log unreadable after submission: {error}; pending.json kept")
            new_turns = [t for t in codexlog.turn_states(recs) if t not in known]
            if len(new_turns) > 1:
                return refuse(f"more than one new turn appeared {new_turns}; pending.json kept")
            if not new_turns:
                continue
            turn = new_turns[0]
            texts = [text for _i, t, text in codexlog.composer_messages(recs) if t == turn]
            if not texts:
                continue
            if len(texts) != 1 or codexlog.canonical(texts[0]) != prompt:
                return refuse(f"new turn {turn} does not carry the submitted prompt; pending.json kept")
            # The turn ID is durable before the marker goes.
            write_durably(turn_dir / "turn-id", turn + "\n")
            PENDING.unlink()
            fsync_dir(PENDING.parent)
            print(f"queued; turn {turn} started with the submitted prompt")
            return 0
        return refuse(
            f"the submitted turn was not observed within {os.environ.get('S0_QUEUE_TIMEOUT', '300')} s; pending.json kept"
        )


if __name__ == "__main__":
    sys.exit(main())
