# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box characterization of per-turn usage reporting — agent-cycle project

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .conftest import PYTHON, ROOT, IsolatedEnvironment
from .rollout import record, task_complete, token_count, write_records

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path
    from typing import Any

USAGE = ROOT / "bin" / "turn-usage.py"


def claude_message(timestamp: str, message_id: str, usage: Mapping[str, int]) -> dict[str, object]:
    """Build one generated Claude Code transcript entry."""
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "uuid": f"generated-{message_id}",
        "message": {"id": message_id, "usage": dict(usage)},
    }


def write_json_lines(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    """Write a generated transcript as JSONL."""
    path.write_text("".join(f"{json.dumps(item)}\n" for item in records), encoding="utf-8")


def usage_values(input_tokens: int, cache_write: int, cache_read: int, output: int) -> dict[str, int]:
    """Build the four Claude Code usage counters."""
    return {
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": cache_write,
        "cache_read_input_tokens": cache_read,
        "output_tokens": output,
    }


def make_codex_log(path: Path) -> int:
    """Write before/after token counts and return the starting line."""
    records = [
        token_count(
            total={"input_tokens": 1_000, "cached_input_tokens": 200, "output_tokens": 100},
            last={"input_tokens": 50},
            primary_used=80,
            secondary_used=30,
        ),
        record("turn_context", {"generated": True}),
        token_count(
            total={"input_tokens": 1_200, "cached_input_tokens": 250, "output_tokens": 140},
            last={"input_tokens": 300},
            primary_used=90,
            secondary_used=31,
        ),
        token_count(
            total={"input_tokens": 1_400, "cached_input_tokens": 300, "output_tokens": 190},
            last={"input_tokens": 100},
            primary_used=10,
            secondary_used=33,
        ),
        token_count(
            total={"input_tokens": 1_600, "cached_input_tokens": 350, "output_tokens": 250},
            last={"input_tokens": 200},
            primary_used=20,
            secondary_used=35,
        ),
        task_complete("turn-generated"),
        token_count(
            total={"input_tokens": 9_999, "cached_input_tokens": 9_999, "output_tokens": 9_999},
            last={"input_tokens": 9_999},
            primary_used=99,
            secondary_used=99,
        ),
    ]
    write_records(path, records)
    return 2


def make_turn(
    path: Path,
    log: Path,
    start_line: int,
    *,
    started: str,
    finished: str,
) -> None:
    """Write the per-turn evidence consumed by turn-usage.py."""
    path.mkdir()
    (path / "thread-log-path").write_text(f"{log}\n", encoding="utf-8")
    (path / "thread-log-lines-before").write_text(f"{start_line}\n", encoding="utf-8")
    (path / "started").write_text(f"{started}\n", encoding="utf-8")
    (path / "finished").write_text(f"{finished}\n", encoding="utf-8")


def test_reports_codex_and_deduplicated_claude_cycles(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Columns and JSON reflect rate resets, token deltas, medians and cycle boundaries."""
    log = tmp_path / "rollout-generated.jsonl"
    start_line = make_codex_log(log)
    turn_one = tmp_path / "turn-001"
    turn_two = tmp_path / "turn-002"
    make_turn(
        turn_one,
        log,
        start_line,
        started="2040-01-02 10:00:00 +0000",
        finished="2040-01-02 10:10:00 +0000",
    )
    make_turn(
        turn_two,
        log,
        start_line,
        started="2040-01-02 10:20:00 +0000",
        finished="2040-01-02 10:30:00 +0000",
    )
    transcript = tmp_path / "claude-generated.jsonl"
    write_json_lines(
        transcript,
        [
            claude_message("2040-01-02T10:01:00Z", "message-one", usage_values(10, 2, 3, 4)),
            claude_message("2040-01-02T10:02:00Z", "message-one", usage_values(20, 4, 6, 8)),
            claude_message("2040-01-02T10:03:00Z", "message-two", usage_values(30, 5, 7, 9)),
            claude_message("2040-01-02T10:15:00Z", "between-turns", usage_values(7, 1, 2, 3)),
            claude_message("2040-01-02T10:31:00Z", "too-late", usage_values(999, 0, 0, 0)),
        ],
    )
    (isolated_env.home / ".claude.json").write_text(
        json.dumps(
            {
                "cachedUsageUtilization": {
                    "fetchedAtMs": 2_208_988_800_000,
                    "utilization": {
                        "five_hour": {"utilization": 12.5},
                        "seven_day": {"utilization": 34.5},
                    },
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, turn_one, turn_two])

    assert result.returncode == 0, result.stderr
    assert (
        "| turn-001 | 80 → 20 (window reset) | 30 → 35 | 450 / 150 / 150 | 200 | 59 / 13 / 17 (2) | 42 |"
        in result.stdout
    )
    first = json.loads((turn_one / "usage.json").read_text(encoding="utf-8"))
    assert first["codex"]["tokens"] == {
        "input_tokens": 600,
        "cached_input_tokens": 150,
        "output_tokens": 150,
    }
    assert first["codex"]["calls"] == 3
    assert first["codex"]["median_input_per_call"] == 200
    assert first["claude_code"]["tokens"]["messages"] == 2
    assert first["claude_code"]["cached_utilization"]["five_hour"] == 12.5
    assert first["claude_code"]["cached_utilization"]["weekly"] == 34.5

    second = json.loads((turn_two / "usage.json").read_text(encoding="utf-8"))
    assert second["claude_window_start"] == "2040-01-02T10:10:00+00:00"
    assert second["claude_code"]["tokens"] == {
        "input_tokens": 7,
        "cache_creation_input_tokens": 1,
        "cache_read_input_tokens": 2,
        "output_tokens": 3,
        "messages": 1,
        "median_context_per_message": 10,
    }


def test_missing_claude_cache_produces_empty_cached_utilization(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """The report remains usable when the optional home cache is absent."""
    log = tmp_path / "rollout-generated.jsonl"
    turn = tmp_path / "turn-001"
    make_turn(
        turn,
        log,
        make_codex_log(log),
        started="2040-01-02 10:00:00 +0000",
        finished="2040-01-02 10:10:00 +0000",
    )
    transcript = tmp_path / "claude-generated.jsonl"
    write_json_lines(transcript, [])

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, turn])

    assert result.returncode == 0, result.stderr
    usage = json.loads((turn / "usage.json").read_text(encoding="utf-8"))
    assert usage["claude_code"]["cached_utilization"] == {}
