#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Fake Codex queue CLI for generated-log tests — agent-cycle project

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

STAMP = "2040-01-02T03:04:05Z"


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


def main() -> int:
    """Emulate the subset of ``codex queue`` used by the wrapper."""
    if len(sys.argv) < 6 or sys.argv[1:4:2] != ["queue", "--thread"] or sys.argv[4] != "--message":
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
