<!--
Copyright (C) 2026 Maxime P. DEMENTYEV
SPDX-License-Identifier: GPL-3.0-only
-->

# agent-cycle

Tooling for a reviewer-implementer pair of AI coding agents, whose guards
fail closed. One agent drives and reviews; the other implements, one test-first
RED/GREEN pair at a time; a person decides everything that is theirs. The
driver queues each turn into the implementer's visible chat, audits the
commands the implementer escalated, snapshots the repositories, and
reviews the commits by reproducing them. Nothing either agent reports is
accepted on its word.

Today the driver is Claude Code and the implementer is Codex, in its VS Code
chat. The process is project-agnostic: each project has its own
implementer chat and its own state directory. The first project served is
[check_rst](https://github.com/dememax/check_rst); the second is this
repository itself.

## Status

- **In use:** stage "S0+": the driver queues every turn itself, and nobody
  relays messages.
- **Tests:** `python3.14 -m pytest` characterizes the tools' refusal paths
  with generated logs and a fake Codex CLI only.
- **Done in the first work package:** the tests, and a fail-closed parser
  for the audit's escalation detection.
- **Next in it:** the push gate, the remaining lint findings, and project
  profiles replacing the two environment variables (below). See
  [AGENTS.md](AGENTS.md).

## Documentation

In reStructuredText, built with Sphinx from `docs/`: the design (roles,
principles, contracts, guards), the stages of automation, the procedure for
one turn, session renewal and bootstrap, the token economy, and review
practices.

## Warnings

- **The tools read undocumented formats:** Codex's rollout logs
  (`~/.codex/sessions/**/rollout-*.jsonl`) and Claude Code's session
  transcripts. Neither is a public contract, and a CLI update can change
  them. The shared reader (`bin/codexlog.py`) fails closed: a malformed
  line or an unexpected structure stops the tool instead of being skipped.
- **The guards are not a sandbox.** The implementer may escalate only
  `git add` and `git commit` in the project's repository; that rule is an
  instruction. After each turn the audit lists the escalated commands within
  its scope: every structured function call, and every source tool call
  whose text names the escalation property. It fails closed on anything
  there it cannot parse unambiguously; a property name built by
  concatenation or encoding is outside its scope. Repository snapshots are
  compared too. The guards detect violations within their documented scope,
  after the fact; they prevent nothing, and a violation outside that scope
  can go unseen. An approved escalation runs outside the implementer's
  sandbox.

## Tools

| Tool | Purpose |
|---|---|
| `bin/codex-identify-thread.py` | Identify a newly created visible Codex chat by its first message, fail-closed, and check its settings against the previous chat's |
| `bin/codex-queue-turn.sh` | Queue one turn into the single active chat, under a lock, refusing on any mismatch; implemented in `codex-queue-turn.py` |
| `bin/audit-turn.py` | After a turn: list escalated commands, extract the final message, check its top-level keys and enum values against a result schema |
| `bin/github-snapshot.sh` | Snapshot the HEAD, refs and status of each repository under `~/github/*/` and `~/github/*/*/`, before and after a turn (best-effort: a failing `git` command is not detected yet) |
| `bin/turn-usage.py` | Per-turn usage of both agents: tokens, context per call, rate-limit windows (best-effort: malformed lines are skipped) |
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
