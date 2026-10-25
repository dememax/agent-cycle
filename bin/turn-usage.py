#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Per-turn usage statistics for both agents — agent-cycle project
"""Per-turn usage statistics for the S0 agent cycle.

Usage: turn-usage.py CLAUDE_TRANSCRIPT TURN_DIR [TURN_DIR ...]

For each turn directory (with thread-log-path, thread-log-lines-before,
started, finished), write usage.json and print one table row.

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

import json
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


def main() -> int:
    transcript = Path(sys.argv[1])
    turns = [Path(p) for p in sys.argv[2:]]
    previous_end = None
    print(
        "| turn | Codex 5h % | Codex week % | Codex tokens in / cached / out | Codex median context/call | Claude tokens in+cache-write / cache-read / out (msgs) | Claude median context/msg |"
    )
    print("|---|---|---|---|---|---|---|")
    for turn in turns:
        try:
            log = Path((turn / "thread-log-path").read_text().strip())
            start = int((turn / "thread-log-lines-before").read_text().strip())
        except OSError, ValueError:
            continue
        started = local_time(turn / "started")
        finished = local_time(turn / "finished")
        codex = codex_usage(log, start)
        since = previous_end or started
        claude = claude_usage(
            transcript,
            since.astimezone(UTC) if since else None,
            finished.astimezone(UTC) if finished else None,
        )
        previous_end = finished
        result = {
            "turn": turn.name,
            "started": started.isoformat() if started else None,
            "finished": finished.isoformat() if finished else None,
            "claude_window_start": since.isoformat() if since else None,
            "codex": codex,
            "claude_code": claude,
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
