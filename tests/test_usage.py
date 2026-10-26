# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box characterization of per-turn usage reporting — agent-cycle project

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

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


def with_context_window(item: dict[str, object], context_window: int) -> dict[str, object]:
    """Add the model context window to a generated token-count record."""
    payload = item["payload"]
    assert isinstance(payload, dict)
    info = payload["info"]
    assert isinstance(info, dict)
    info["model_context_window"] = context_window
    return item


def make_turn(
    path: Path,
    log: Path,
    start_line: int,
    *,
    started: str,
    finished: str,
    turn_id: str = "turn-generated",
) -> None:
    """Write the per-turn evidence consumed by turn-usage.py."""
    path.mkdir()
    (path / "thread-log-path").write_text(f"{log}\n", encoding="utf-8")
    (path / "thread-log-lines-before").write_text(f"{start_line}\n", encoding="utf-8")
    (path / "started").write_text(f"{started}\n", encoding="utf-8")
    (path / "finished").write_text(f"{finished}\n", encoding="utf-8")
    (path / "turn-id").write_text(f"{turn_id}\n", encoding="utf-8")


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

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, turn_one])

    assert result.returncode == 0, result.stderr
    table_row = "| turn-001 | 80 → 20 (window reset) | 30 → 35 | 450 / 150 / 150 | 200 | 59 / 13 / 17 (2) | 42 |"
    assert result.stdout.splitlines()[2] == table_row
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
    assert first["claude_window_start_source"] == "started"

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, "--previous", turn_one, turn_two])
    assert result.returncode == 0, result.stderr
    second = json.loads((turn_two / "usage.json").read_text(encoding="utf-8"))
    assert second["claude_window_start"] == "2040-01-02T10:10:00+00:00"
    assert second["claude_window_start_source"] == "previous"
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
    assert usage["claude_window_start"] == "2040-01-02T10:00:00+00:00"
    assert usage["claude_window_start_source"] == "started"


def test_previous_turn_usage_is_never_rewritten(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """The optional previous turn is read-only input, never another output target."""
    log = tmp_path / "rollout-generated.jsonl"
    start_line = make_codex_log(log)
    previous = tmp_path / "turn-previous"
    current = tmp_path / "turn-current"
    make_turn(
        previous,
        log,
        start_line,
        started="2040-01-02 09:00:00 +0000",
        finished="2040-01-02 09:10:00 +0000",
    )
    make_turn(
        current,
        log,
        start_line,
        started="2040-01-02 09:20:00 +0000",
        finished="2040-01-02 09:30:00 +0000",
    )
    previous_bytes = b'{"generated":"must stay byte-identical"}\n'
    (previous / "usage.json").write_bytes(previous_bytes)
    transcript = tmp_path / "claude-generated.jsonl"
    write_json_lines(transcript, [])

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, "--previous", previous, current])

    assert result.returncode == 0, result.stderr
    assert (previous / "usage.json").read_bytes() == previous_bytes
    assert (current / "usage.json").exists()


def test_multiple_turn_directories_are_a_usage_error(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """The new interface has exactly one output turn directory."""
    log = tmp_path / "rollout-generated.jsonl"
    start_line = make_codex_log(log)
    first = tmp_path / "turn-first"
    second = tmp_path / "turn-second"
    for turn in (first, second):
        make_turn(
            turn,
            log,
            start_line,
            started="2040-01-02 10:00:00 +0000",
            finished="2040-01-02 10:10:00 +0000",
        )
    transcript = tmp_path / "claude-generated.jsonl"
    write_json_lines(transcript, [])

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, first, second])

    assert result.returncode == 2
    assert not (first / "usage.json").exists()
    assert not (second / "usage.json").exists()


def test_unreadable_previous_turn_is_a_usage_error(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """A previous turn without a readable finish time cannot define the window."""
    log = tmp_path / "rollout-generated.jsonl"
    current = tmp_path / "turn-current"
    make_turn(
        current,
        log,
        make_codex_log(log),
        started="2040-01-02 10:00:00 +0000",
        finished="2040-01-02 10:10:00 +0000",
    )
    transcript = tmp_path / "claude-generated.jsonl"
    write_json_lines(transcript, [])

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, "--previous", tmp_path / "missing-turn", current])

    assert result.returncode == 2
    assert not (current / "usage.json").exists()


@pytest.mark.parametrize(
    "broken_input",
    [
        "missing-log-path",
        "unreadable-log-path",
        "missing-start-line",
        "unreadable-start-line",
        "noninteger-start-line",
    ],
)
def test_unusable_current_turn_log_evidence_is_a_usage_error(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    broken_input: str,
) -> None:
    """Required current-turn log evidence is validated before any output."""
    log = tmp_path / "rollout-generated.jsonl"
    turn = tmp_path / "turn-current"
    make_turn(
        turn,
        log,
        make_codex_log(log),
        started="2040-01-02 10:00:00 +0000",
        finished="2040-01-02 10:10:00 +0000",
    )
    transcript = tmp_path / "claude-generated.jsonl"
    write_json_lines(transcript, [])
    evidence_name = "thread-log-path" if broken_input.endswith("log-path") else "thread-log-lines-before"
    evidence = turn / evidence_name
    if broken_input.startswith("missing"):
        evidence.unlink()
    elif broken_input.startswith("unreadable"):
        evidence.unlink()
        evidence.mkdir()
    else:
        evidence.write_text("not an integer\n", encoding="utf-8")

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, turn])

    assert result.returncode == 2
    assert result.stdout == ""
    assert str(evidence) in result.stderr
    assert not (turn / "usage.json").exists()


def test_renewal_compaction_buckets_and_third_compaction_trigger(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
) -> None:
    """Compactions are bucketed by exact log line and accumulated for renewal."""
    log = tmp_path / "rollout-generated.jsonl"
    records = [
        record("compacted", {"generated": "earlier"}),
        task_complete("turn-previous"),
        record("compacted", {"generated": "between"}),
        record("turn_context", {"generated": True}),
        record("compacted", {"generated": "inside"}),
        with_context_window(
            token_count(
                total={"input_tokens": 70, "cached_input_tokens": 0, "output_tokens": 1},
                last={"input_tokens": 70},
                primary_used=1,
                secondary_used=2,
            ),
            100,
        ),
        task_complete("turn-current"),
    ]
    write_records(log, records)
    previous = tmp_path / "turn-previous"
    current = tmp_path / "turn-current"
    make_turn(
        previous,
        log,
        0,
        started="2040-01-02 09:00:00 +0000",
        finished="2040-01-02 09:10:00 +0000",
        turn_id="turn-previous",
    )
    make_turn(
        current,
        log,
        4,
        started="2040-01-02 09:20:00 +0000",
        finished="2040-01-02 09:30:00 +0000",
        turn_id="turn-current",
    )
    transcript = tmp_path / "claude-generated.jsonl"
    write_json_lines(transcript, [])

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, "--previous", previous, current])

    assert result.returncode == 0, result.stderr
    usage = json.loads((current / "usage.json").read_text(encoding="utf-8"))
    renewal = usage["renewal"]
    assert renewal["compactions_in_turn"] == [5]
    assert renewal["compactions_between_turns"] == [3]
    assert renewal["compactions_in_thread"] == [1, 3, 5]
    assert renewal["max_input_per_call"] == 70
    assert renewal["context_window"] == 100
    assert renewal["max_input_percentage"] == 70
    assert "compaction_in_turn" in renewal["triggers"]
    assert "three_compactions_in_thread" in renewal["triggers"]
    assert result.stdout.splitlines()[-1].startswith("renewal: ")


@pytest.mark.parametrize("with_previous_usage", [True, False], ids=["known-previous", "unknown-previous"])
def test_renewal_maximum_and_consecutive_median_rules(
    isolated_env: IsolatedEnvironment,
    tmp_path: Path,
    *,
    with_previous_usage: bool,
) -> None:
    """Immediate and consecutive median triggers use current and saved prior facts."""
    before = token_count(
        total={"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10},
        last={"input_tokens": 10},
        primary_used=1,
        secondary_used=2,
    )
    current_count = with_context_window(
        token_count(
            total={"input_tokens": 810_101, "cached_input_tokens": 0, "output_tokens": 20},
            last={"input_tokens": 810_001},
            primary_used=2,
            secondary_used=3,
        ),
        1_000_000,
    )
    log = tmp_path / "rollout-generated.jsonl"
    write_records(log, [before, current_count, task_complete("turn-current")])
    previous_log = tmp_path / "previous-rollout-generated.jsonl"
    write_records(previous_log, [])
    previous = tmp_path / "turn-previous"
    current = tmp_path / "turn-current"
    make_turn(
        previous,
        previous_log,
        0,
        started="2040-01-02 09:00:00 +0000",
        finished="2040-01-02 10:00:00 +0000",
        turn_id="turn-previous",
    )
    make_turn(
        current,
        log,
        1,
        started="2040-01-02 10:01:00 +0000",
        finished="2040-01-02 10:10:00 +0000",
        turn_id="turn-current",
    )
    if with_previous_usage:
        (previous / "usage.json").write_text(
            json.dumps(
                {
                    "renewal": {
                        "codex_upper_median": 160_000,
                        "claude_median_context": 310_000,
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
    transcript = tmp_path / "claude-generated.jsonl"
    write_json_lines(
        transcript,
        [claude_message("2040-01-02T10:05:00Z", "large-message", usage_values(310_001, 0, 0, 1))],
    )

    result = isolated_env.run([PYTHON, "-I", USAGE, transcript, "--previous", previous, current])

    assert result.returncode == 0, result.stderr
    renewal = json.loads((current / "usage.json").read_text(encoding="utf-8"))["renewal"]
    assert renewal["max_input_per_call"] == 810_001
    assert renewal["context_window"] == 1_000_000
    assert renewal["max_input_percentage"] == pytest.approx(81.0001)
    assert renewal["codex_upper_median"] == 810_001
    assert renewal["claude_median_context"] == 310_001
    assert "max_input_per_call_above_80_percent" in renewal["triggers"]
    if with_previous_usage:
        assert "codex_upper_median_two_consecutive_turns" in renewal["triggers"]
        assert "claude_median_context_two_consecutive_turns" in renewal["triggers"]
    else:
        assert "codex_upper_median_two_consecutive_turns" not in renewal["triggers"]
        assert "claude_median_context_two_consecutive_turns" not in renewal["triggers"]
        assert any("previous Codex upper median" in note for note in renewal["notes"])
        assert any("previous Claude median context" in note for note in renewal["notes"])
