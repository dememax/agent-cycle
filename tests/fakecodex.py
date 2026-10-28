#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Fake Codex queue CLI for generated-log tests — agent-cycle project

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

STAMP = "2040-01-02T03:04:05Z"
CLI_VERSION = "0.162.0-alpha.17.2"


def line(record_type: str, payload: dict[str, object]) -> str:
    """Serialize one generated rollout record."""
    return json.dumps({"timestamp": STAMP, "type": record_type, "payload": payload}) + "\n"


def started(turn_id: str) -> str:
    """Serialize a generated task-started event."""
    return line("event_msg", {"type": "task_started", "turn_id": turn_id})


def composer(turn_id: str, text: str) -> str:
    """Serialize a generated composer message."""
    return line(
        "response_item",
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": text}],
            "internal_chat_message_metadata_passthrough": {
                "turn_id": turn_id,
                "content_item_kinds": ["user.text"],
            },
        },
    )


def append(path: Path, text: str) -> None:
    """Append one stage of an asynchronously generated rollout."""
    with path.open("a", encoding="utf-8") as stream:
        stream.write(text)


def worker(mode: str, log: Path, message: str, delay: float) -> int:
    """Write delayed stages after the queue command itself has returned."""
    if mode.startswith("partial"):
        append(log, started("turn-delayed").removesuffix("\n"))
        if mode == "partial_forever":
            return 0
        time.sleep(delay)
        append(log, "\n" + composer("turn-delayed", message))
        return 0
    append(log, started("turn-delayed"))
    if mode == "started_only":
        return 0
    time.sleep(delay)
    append(log, composer("turn-delayed", message))
    return 0


def main() -> int:
    """Emulate the subset of ``codex queue`` used by the wrapper."""
    if sys.argv[1:] == ["--version"]:
        print(os.environ.get("FAKE_CODEX_VERSION_OUTPUT", f"codex-cli {CLI_VERSION}"))
        return 0
    if len(sys.argv) == 6 and sys.argv[1] == "--worker":
        return worker(sys.argv[2], Path(sys.argv[3]), sys.argv[4], float(sys.argv[5]))
    if len(sys.argv) != 6 or sys.argv[1] != "queue" or sys.argv[2] != "--thread" or sys.argv[4] != "--message":
        print("unsupported fake invocation", file=sys.stderr)
        return 2
    message = sys.argv[5]
    mode = os.environ["FAKE_CODEX_MODE"]
    log = Path(os.environ["FAKE_CODEX_LOG"])
    if mode == "hang":
        time.sleep(60)
        return 0
    if mode == "nonzero":
        print("selected fake failure", file=sys.stderr)
        return 23
    if mode in {"partial_then_turn", "partial_forever", "started_then_composer", "started_only"}:
        subprocess.Popen(
            [
                sys.executable,
                __file__,
                "--worker",
                mode,
                str(log),
                message,
                os.environ.get("FAKE_CODEX_STAGE_DELAY", "3.4"),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        print("queued by fake codex")
        return 0
    time.sleep(float(os.environ.get("FAKE_CODEX_DELAY", "0.01")))
    additions = ""
    if mode == "turn":
        additions = started("turn-new") + composer("turn-new", message)
    elif mode == "foreign":
        additions = started("turn-foreign") + composer("turn-foreign", "foreign prompt")
    elif mode == "two":
        additions = started("turn-one") + started("turn-two")
    elif mode == "malformed":
        additions = "{not JSON\n"
    elif mode == "rewrite":
        Path(os.environ["FAKE_CODEX_PROMPT"]).write_text("rewritten after submission\n", encoding="utf-8")
        additions = started("turn-rewrite") + composer("turn-rewrite", message)
    elif mode == "duplicate_composer":
        additions = (
            started("turn-duplicate") + composer("turn-duplicate", message) + composer("turn-duplicate", message)
        )
    elif mode != "none":
        print(f"unknown fake mode: {mode}", file=sys.stderr)
        return 2
    if additions:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(additions)
    print("queued by fake codex")
    return 0


if __name__ == "__main__":
    sys.exit(main())
