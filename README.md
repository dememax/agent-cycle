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
- **Done in the first work package:** the tests, a fail-closed parser for the
  audit's escalation detection, and the public-content push gate.
- **Next in it:** make snapshots fail on Git errors, validate complete audit
  results, resolve the remaining lint findings, and add project profiles that
  replace the two environment variables (below). See [AGENTS.md](AGENTS.md).

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
| `tools/check-public.sh` | Fail closed on protected patterns in the content and metadata a push would publish |
| `tools/pre-push` | Tracked Git hook that applies the public-content gate to proposed ref updates |
| `tools/install-gate.sh` | Install the gate from a selected commit into an external, versioned directory |
| `schemas/*.json` | The implementer's and the reviewer's final-message contracts |

Run state (the active-chat record, the turn directories, the evidence)
lives outside the repository, in `~/.local/state/agent-cycle/<project>/`.

## Public-content push gate

`tools/check-public.sh RANGE...` scans one or more revision ranges. A single
revision means every commit reachable from it. For every selected commit, the
gate scans:

- every range-specific blob reported by `git rev-list --objects`, including a
  blob added and removed within the range;
- changed path names;
- the complete commit message; and
- the author and committer names and email addresses.

`tools/check-public.sh --pre-push REMOTE` reads Git's pre-push records from
standard input. It scans the objects added by an update, excludes that remote's
tracking history for a new ref, and scans nothing for a deletion. When the
local object is an annotated tag, its message and tagger name and email address
are scanned too.

The real deny-list is deliberately outside this public repository. Its default
location is `~/.config/agent-cycle/deny-list`; `AGENT_CYCLE_DENY_LIST` can
select another file. Blank lines and lines beginning with `#` are ignored.
Every other line has the form `KIND:VALUE`:

- `fixed-i` is a case-insensitive substring;
- `word` is a case-sensitive whole word; and
- `regex` is a Python regular expression and may use inline flags.

In addition, the gate rejects literal absolute home-directory paths under
`/home` or `/Users` (but not placeholders such as `/home/<user>`), email
addresses other than Git's configured `user.email` and the two co-author
addresses named in [AGENTS.md](AGENTS.md), and these account-identifier keys
when they have a value on the same line: `creator_user_id`,
`creator_account_id`, `account_id`, `accountUuid`, `organizationUuid`,
`userID` and `user_id`.

Do not point `core.hooksPath` into the work tree: checking out a commit that
does not contain the hook would silently disable it. Instead, install an
approved commit into a new directory outside the repository. The revision
defaults to `HEAD`; `--rev REV` selects one explicitly:

```bash
tools/install-gate.sh --rev APPROVED_REV ~/.local/lib/agent-cycle/gate-REVISION
```

The installer resolves the revision to a full commit and reads
`check-public.sh`, `check-public.py` and `pre-push` from that commit with Git,
not from the work tree. It makes them executable and writes `REVISION` and
`SHA256SUMS` beside them. It refuses a non-empty destination, a destination
inside this work tree, an unresolved revision, or any failed Git command. It
does not alter Git configuration; on success it prints the
`git config core.hooksPath DEST` command for the person to run.

Hooks are configured per clone. After running the printed command, verify both
the configured path and the hook file:

```bash
DEST=~/.local/lib/agent-cycle/gate-REVISION
git config core.hooksPath
test -x "$DEST/pre-push"
```

Reinstall every approved gate change into a new `DEST`, then update
`core.hooksPath` to that directory. If the configured directory or hook is
missing, Git runs no hook. `git push --no-verify` also skips it. The push itself
remains a person's action.

Exit status 0 means the complete requested scan was clean, 1 means it found a
protected pattern, and 2 means it refused to scan. Refusals include a missing,
unreadable or empty deny-list; an unknown kind, empty value or invalid regular
expression; an invalid revision; a failed Git command; and malformed pre-push
input. Findings identify the commit, item kind, rule and location without
printing the matching text or deny-list value. There is no inline exception or
suppression mechanism: fix a false positive in the text or in the private
deny-list.

Blob bytes are decoded as UTF-8 while preserving undecodable bytes before the
text patterns run. The scanner does not decode UTF-16, decompress content, or
reconstruct a literal value split across lines or source-code string
concatenations; a purpose-written regular expression can cover some textual
variants. More generally, the gate cannot recognize a sensitive value that no
rule describes, cannot establish that a push contains no private information,
and is not a sandbox. Its per-clone hook can be absent or bypassed as described
above. Review and the rule that only a person pushes remain necessary.

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
