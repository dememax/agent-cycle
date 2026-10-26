#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Per-turn usage statistics for both agents — agent-cycle project
"""Per-turn usage statistics for the S0 agent cycle.

Usage: turn-usage.py CLAUDE_TRANSCRIPT [--previous PREVIOUS_TURN_DIR] TURN_DIR

For the turn directory (with thread-log-path, thread-log-lines-before,
started, finished and turn-id), write usage.json and print one table row
followed by one renewal-facts line.  A previous turn is read-only input.

Codex: the 5-hour (primary) and weekly (secondary) used_percent of the
"codex" limit before the turn and at its end, and the token totals the
turn consumed, from the thread's rollout log.

Claude Code: the tokens of the driver's own messages in the turn's cycle,
from the end of the previous turn to the end of this one (review,
prompt and waiting), deduplicated by message id; and the cached
utilization in ~/.claude.json with its fetch time, which Claude Code
refreshes only occasionally, so its age is reported.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path


def local_time(path: Path) -> datetime | None:
    try:
        return datetime.strptime(path.read_text().strip(), "%Y-%m-%d %H:%M:%S %z")
    except OSError, ValueError:
        return None


def codex_usage(log: Path, start_line: int) -> dict[str, object]:
    before = None
    end = None
    tokens_before = None
    tokens_end = None
    per_call: list[int] = []
    with log.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") or {}
            if number > start_line and payload.get("type") == "task_complete":
                break
            if payload.get("type") != "token_count":
                continue
            info = payload.get("info") or {}
            total = info.get("total_token_usage")
            limits = payload.get("rate_limits") or {}
            usable = limits.get("limit_id") == "codex" and limits.get("primary")
            if number <= start_line:
                if total:
                    tokens_before = total
                if usable:
                    before = limits
            else:
                if total:
                    tokens_end = total
                last = info.get("last_token_usage") or {}
                if last.get("input_tokens"):
                    per_call.append(int(last["input_tokens"]))
                if usable:
                    end = limits

    def pct(limits: dict | None, key: str) -> float | None:
        return None if not limits or not limits.get(key) else limits[key]["used_percent"]

    delta = {}
    if tokens_end:
        base = tokens_before or {}
        delta = {k: tokens_end[k] - base.get(k, 0) for k in tokens_end}
    return {
        "five_hour_before": pct(before, "primary"),
        "five_hour_after": pct(end, "primary"),
        "weekly_before": pct(before, "secondary"),
        "weekly_after": pct(end, "secondary"),
        "five_hour_resets_at": (
            datetime.fromtimestamp(end["primary"]["resets_at"]).astimezone().isoformat(timespec="minutes")
            if end and end.get("primary") and end["primary"].get("resets_at")
            else None
        ),
        "tokens": delta,
        "calls": len(per_call),
        "median_input_per_call": sorted(per_call)[len(per_call) // 2] if per_call else None,
    }


def claude_usage(transcript: Path, since: datetime | None, until: datetime | None) -> dict[str, object]:
    seen: dict[str, dict] = {}
    with transcript.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") != "assistant":
                continue
            message = record.get("message") or {}
            usage = message.get("usage")
            stamp = record.get("timestamp")
            if not usage or not stamp:
                continue
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if (since and when <= since) or (until and when > until):
                continue
            seen[message.get("id") or record.get("uuid")] = usage
    contexts = sorted(
        int(u.get("input_tokens") or 0)
        + int(u.get("cache_creation_input_tokens") or 0)
        + int(u.get("cache_read_input_tokens") or 0)
        for u in seen.values()
    )
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")
    totals = {k: sum(int(u.get(k) or 0) for u in seen.values()) for k in keys}
    totals["messages"] = len(seen)
    totals["median_context_per_message"] = contexts[len(contexts) // 2] if contexts else None
    cached = {}
    try:
        data = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
        util = data.get("cachedUsageUtilization") or {}
        fetched = util.get("fetchedAtMs")
        u = util.get("utilization") or {}
        cached = {
            "five_hour": (u.get("five_hour") or {}).get("utilization"),
            "weekly": (u.get("seven_day") or {}).get("utilization"),
            "fetched_at": (
                datetime.fromtimestamp(fetched / 1000).astimezone().isoformat(timespec="minutes") if fetched else None
            ),
        }
    except OSError, ValueError:
        pass
    return {"tokens": totals, "cached_utilization": cached}


def fmt(value: object) -> str:
    return "?" if value is None else f"{value:g}" if isinstance(value, float) else str(value)


def rollout_records(log: Path) -> list[tuple[int, dict[str, object]]]:
    """Read usable object records and their physical JSONL line numbers."""
    records = []
    try:
        with log.open(encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict):
                    records.append((number, record))
    except OSError:
        pass
    return records


def payload(record: dict[str, object]) -> dict[str, object]:
    """Return an object payload, or an empty object for an unusable one."""
    value = record.get("payload")
    return value if isinstance(value, dict) else {}


def finite_number(value: object) -> int | float | None:
    """Return a finite JSON number, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return value


def saved_medians(previous: Path | None) -> tuple[int | float | None, int | float | None]:
    """Read renewal medians, including usage files made before renewal facts existed."""
    if previous is None:
        return None, None
    try:
        saved = json.loads((previous / "usage.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None, None
    if not isinstance(saved, dict):
        return None, None
    renewal = saved.get("renewal")
    if isinstance(renewal, dict):
        codex = finite_number(renewal.get("codex_upper_median"))
        claude = finite_number(renewal.get("claude_median_context"))
    else:
        codex = None
        claude = None
    old_codex = saved.get("codex")
    if codex is None and isinstance(old_codex, dict):
        codex = finite_number(old_codex.get("median_input_per_call"))
    old_claude = saved.get("claude_code")
    if claude is None and isinstance(old_claude, dict):
        old_tokens = old_claude.get("tokens")
        if isinstance(old_tokens, dict):
            claude = finite_number(old_tokens.get("median_context_per_message"))
    return codex, claude


def task_end(
    records: list[tuple[int, dict[str, object]]],
    turn_id: str | None,
    *,
    after: int,
    through: int | None = None,
) -> int | None:
    """Find a named turn's first task-complete line in a bounded range."""
    if turn_id is None:
        return None
    for number, record in records:
        item = payload(record)
        if (
            number > after
            and (through is None or number <= through)
            and item.get("type") == "task_complete"
            and item.get("turn_id") == turn_id
        ):
            return number
    return None


def turn_text(turn: Path, name: str) -> str | None:
    """Read a non-empty turn evidence field."""
    try:
        value = (turn / name).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def renewal_facts(
    turn: Path,
    previous: Path | None,
    log: Path,
    start: int,
    codex: dict[str, object],
    claude: dict[str, object],
) -> dict[str, object]:
    """Collect renewal evidence, preserving unknowns rather than guessing."""
    notes: list[str] = []
    triggers: list[str] = []
    records = rollout_records(log)
    current_id = turn_text(turn, "turn-id")
    end = task_end(records, current_id, after=start)

    compactions_in_turn: list[int] | None = None
    compactions_in_thread: list[int] | None = None
    maximum: int | float | None = None
    context_window: int | float | None = None
    if end is None:
        notes.append("current task_complete is unavailable; in-turn and thread renewal facts are unknown")
    else:
        compactions_in_turn = [
            number for number, record in records if start < number <= end and record.get("type") == "compacted"
        ]
        compactions_in_thread = [
            number for number, record in records if number <= end and record.get("type") == "compacted"
        ]
        inputs: list[int | float] = []
        for number, record in records:
            if not start < number <= end:
                continue
            item = payload(record)
            if item.get("type") != "token_count":
                continue
            info = item.get("info")
            if not isinstance(info, dict):
                continue
            last = info.get("last_token_usage")
            if isinstance(last, dict):
                value = finite_number(last.get("input_tokens"))
                if value is not None:
                    inputs.append(value)
            value = finite_number(info.get("model_context_window"))
            if value is not None:
                context_window = value
        maximum = max(inputs) if inputs else None
        if not inputs:
            notes.append("maximum Codex input per call is unavailable")
        if context_window is None:
            notes.append("Codex model context window is unavailable")

    compactions_between_turns: list[int] | None = None
    previous_same_log = False
    if previous is not None:
        previous_log_text = turn_text(previous, "thread-log-path")
        if previous_log_text is not None:
            previous_same_log = Path(previous_log_text).resolve() == log.resolve()
        if previous_same_log:
            previous_id = turn_text(previous, "turn-id")
            previous_end = task_end(records, previous_id, after=0, through=start)
            if previous_end is not None:
                compactions_between_turns = [
                    number
                    for number, record in records
                    if previous_end < number <= start and record.get("type") == "compacted"
                ]
            else:
                notes.append("previous task_complete is unavailable in the current log")
        else:
            notes.append("previous turn is not in the current log; between-turn compactions are unknown")
    else:
        notes.append("no previous turn in the current log; between-turn compactions are unknown")

    percentage = None
    if maximum is not None and context_window is not None and context_window > 0:
        percentage = maximum * 100 / context_window
        if percentage > 80:
            triggers.append("max_input_per_call_above_80_percent")
    elif end is not None and maximum is not None:
        notes.append("Codex input percentage is unavailable because the context window is not positive")

    if compactions_in_turn:
        triggers.append("compaction_in_turn")
    if compactions_in_thread is not None and len(compactions_in_thread) >= 3:
        triggers.append("three_compactions_in_thread")

    codex_median = finite_number(codex.get("median_input_per_call"))
    claude_tokens = claude.get("tokens")
    claude_median = (
        finite_number(claude_tokens.get("median_context_per_message")) if isinstance(claude_tokens, dict) else None
    )
    previous_codex, previous_claude = saved_medians(previous)
    if codex_median is None:
        notes.append("current Codex upper median is unavailable")
    if previous_codex is None:
        notes.append("previous Codex upper median is unavailable; consecutive-turn trigger is unknown")
    if codex_median is not None and previous_codex is not None and codex_median > 150_000 and previous_codex > 150_000:
        triggers.append("codex_upper_median_two_consecutive_turns")
    if claude_median is None:
        notes.append("current Claude median context is unavailable")
    if previous_claude is None:
        notes.append("previous Claude median context is unavailable; consecutive-turn trigger is unknown")
    if (
        claude_median is not None
        and previous_claude is not None
        and claude_median > 300_000
        and previous_claude > 300_000
    ):
        triggers.append("claude_median_context_two_consecutive_turns")

    return {
        "compactions_in_turn": compactions_in_turn,
        "compactions_between_turns": compactions_between_turns,
        "compactions_in_thread": compactions_in_thread,
        "max_input_per_call": maximum,
        "context_window": context_window,
        "max_input_percentage": percentage,
        "codex_upper_median": codex_median,
        "claude_median_context": claude_median,
        "triggers": triggers,
        "notes": notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path, metavar="CLAUDE_TRANSCRIPT")
    parser.add_argument("--previous", type=Path, metavar="PREVIOUS_TURN_DIR")
    parser.add_argument("turn", type=Path, metavar="TURN_DIR")
    args = parser.parse_args()
    transcript: Path = args.transcript
    previous: Path | None = args.previous
    turn: Path = args.turn
    previous_end = local_time(previous / "finished") if previous is not None else None
    if previous is not None and previous_end is None:
        parser.error(f"cannot read previous turn finish time: {previous / 'finished'}")
    print(
        "| turn | Codex 5h % | Codex week % | Codex tokens in / cached / out | Codex median context/call | Claude tokens in+cache-write / cache-read / out (msgs) | Claude median context/msg |"
    )
    print("|---|---|---|---|---|---|---|")
    try:
        log = Path((turn / "thread-log-path").read_text().strip())
        start = int((turn / "thread-log-lines-before").read_text().strip())
    except OSError, ValueError:
        return 0
    started = local_time(turn / "started")
    finished = local_time(turn / "finished")
    codex = codex_usage(log, start)
    since = previous_end or started
    source = "previous" if previous is not None else "started"
    claude = claude_usage(
        transcript,
        since.astimezone(UTC) if since else None,
        finished.astimezone(UTC) if finished else None,
    )
    renewal = renewal_facts(turn, previous, log, start, codex, claude)
    result = {
        "turn": turn.name,
        "started": started.isoformat() if started else None,
        "finished": finished.isoformat() if finished else None,
        "claude_window_start": since.isoformat() if since else None,
        "claude_window_start_source": source,
        "codex": codex,
        "claude_code": claude,
        "renewal": renewal,
    }
    (turn / "usage.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    t = codex["tokens"]
    c = claude["tokens"]
    b, a = codex["five_hour_before"], codex["five_hour_after"]
    reset = " (window reset)" if b is not None and a is not None and a < b else ""
    print(
        f"| {turn.name} | {fmt(b)} → {fmt(a)}{reset}"
        f" | {fmt(codex['weekly_before'])} → {fmt(codex['weekly_after'])}"
        f" | {t.get('input_tokens', 0) - t.get('cached_input_tokens', 0):,} / {t.get('cached_input_tokens', 0):,} / {t.get('output_tokens', 0):,}"
        f" | {fmt(codex['median_input_per_call'])}"
        f" | {c['input_tokens'] + c['cache_creation_input_tokens']:,} / {c['cache_read_input_tokens']:,} / {c['output_tokens']:,} ({c['messages']})"
        f" | {fmt(c['median_context_per_message'])} |"
    )
    print(f"renewal: {json.dumps(renewal, separators=(',', ':'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
