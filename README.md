<!--
Copyright (C) 2026 Maxime P. DEMENTYEV
SPDX-License-Identifier: GPL-3.0-only
-->

# agent-cycle

Tools and procedures for a pair of AI coding agents working on one
repository: one agent drives and reviews, the other implements, one
test-first RED/GREEN pair at a time. The driver queues each turn into the
implementer's visible chat, audits what the implementer did, and reviews
its commits by reproducing them. Nothing the implementer reports is
accepted on its word, and the same holds the other way round.

Today the driver is Claude Code and the implementer is Codex, in its VS Code
chat. The process is meant to be project-agnostic; the first project it
serves is [check_rst](https://github.com/dememax/check_rst).

## Status

**Initial import.** The tools are the ones in use today (stage "S0+": the
driver queues every turn itself, nobody relays messages, and the human
decides only what is theirs), imported as they were reviewed. The project
they serve is selected by two environment variables, which default to
check_rst's (below). Project profiles, the tests and the push gate are the
first work package; see [AGENTS.md](AGENTS.md).

## Warnings

- **The tools read undocumented formats:** Codex's rollout logs
  (`~/.codex/sessions/**/rollout-*.jsonl`) and Claude Code's session
  transcripts. Neither is a public contract, and a CLI update can change
  them. The shared reader (`bin/codexlog.py`) fails closed: a malformed
  line or an unexpected structure stops the tool instead of being skipped.
- **The guards are not a sandbox.** The implementer may escalate only
  `git add` and `git commit` in the project's repository; that rule is an
  instruction. After each turn the audit lists every escalated command and
  repository snapshots are compared, so a violation is found after the
  fact, not prevented. An approved escalation runs outside the
  implementer's sandbox.

## Tools

| Tool | Purpose |
|---|---|
| `bin/codex-identify-thread.py` | Identify a newly created visible Codex chat by its first message, fail-closed, and check its settings against the previous chat's |
| `bin/codex-queue-turn.sh` | Queue one turn into the single active chat, under a lock, refusing on any mismatch; implemented in `codex-queue-turn.py` |
| `bin/audit-turn.py` | After a turn: list escalated commands, extract the final message, validate it against a result schema |
| `bin/github-snapshot.sh` | Snapshot every repository's refs and status, before and after a turn |
| `bin/turn-usage.py` | Per-turn usage of both agents: tokens, context per call, rate-limit windows |
| `bin/codexlog.py` | The strict log reader the tools share |
| `schemas/*.json` | The implementer's and the reviewer's final-message contracts |

Run state (the active-chat record, the turn directories, the evidence)
lives outside the repository, in `~/.local/state/agent-cycle/<project>/`.

## Selecting the project

Each project has its own Codex chat, opened in a VS Code window on that
project's repository, and its own state directory. Two environment
variables select the project; both default to check_rst's:

| Variable | Default | Used for |
|---|---|---|
| `AGENT_CYCLE_REPO` | `~/github/check_rst` | the chat's expected working directory, and the only repository where commits may be escalated |
| `AGENT_CYCLE_STATE` | `~/.local/state/agent-cycle/check_rst` | the active-chat record and the queue lock |

Both must be absolute. For the queue alone, `S0_STATE_DIR`, the older name,
overrides `AGENT_CYCLE_STATE` when it is set; the identifier ignores it.
The queue refuses an active-chat record that belongs to another
repository. A project's first chat is identified against a chat of another
project: its settings are compared after moving that chat's repository
paths to the selected repository, and must otherwise be identical. Project
profiles replace these variables later.

## License

GPL-3.0-only; see [LICENSE](LICENSE).
