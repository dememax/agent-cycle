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

- **Release:** version `0.1.1`; the second work package and token tools
  `TOKENS-1`–`TOKENS-4` are complete.
- **In use:** stage "S0+": the driver queues every turn itself, and nobody
  relays messages.
- **Tests:** `python3.14 -m pytest` characterizes the tools' refusal paths
  with generated logs and a fake Codex CLI only.
- **Done in the first work package:** the tests; the audit's fail-closed
  escalation parser and complete result validation (`AUDIT-2`); the
  public-content push gate, including its clean-pass evidence (`GATE-2`);
  fail-closed repository snapshots, including signal handling (`SNAP1/m1`);
  usage and renewal facts (`USAGE-1`); and the remaining lint findings
  (`LINT-1`). Project profiles now replace the old repository and state
  environment variables (below).

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
| `bin/codex-identify-thread.py` | Identify a new visible Codex chat by its first message, fail-closed, check its effective profile, require explicit acceptance of a changed CLI version, and record that version |
| `bin/codex-queue-turn.sh` | Queue one turn into the single active chat under a lock, enforcing its profile and CLI-version anchors; implemented in `codex-queue-turn.py` |
| `bin/audit-turn.py` | After a turn: list escalated commands, require the final message to be one strict JSON object, and validate it recursively against a result schema |
| `bin/github-snapshot.sh` | Snapshot the HEAD, refs and status of each repository under `~/github/*/` and `~/github/*/*/`, failing closed on an incomplete Git query |
| `bin/turn-usage.py` | One turn's usage and renewal facts for both agents; an optional previous turn is read-only (best-effort: malformed lines are skipped) |
| `bin/read-section.py` | Read one Markdown or reStructuredText section exactly, refusing missing or ambiguous headings and invalid inputs |
| `bin/turn-record.py` | Generate the factual Markdown skeleton of a turn record from its evidence directory, without guessing missing facts |
| `bin/state.py` | Print the generated restart summary, or atomically refresh its JSON and Markdown caches in the selected project's state directory |
| `bin/validate.py` | Run a project's ordered validation steps once, retain their raw output, and print a compact complete summary |
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

Because the email rule is deliberately conservative, it can flag an allowed
address written inside a shell assignment such as `key='<identity>'`; documents
should write identities as placeholders, as [the release procedure](docs/releasing.rst)
does.

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
input. A clean scan prints one line to standard error with the number of
commits and scanned items and the installed gate revision. A scanned item is a
commit message, identity, changed path, blob or tag. The revision is `unknown`
when the scanner is not installed beside a valid `REVISION` file. Findings go
to standard output and identify the commit, item kind, rule and location
without printing the matching text or deny-list value. Refusals go to standard
error. There is no inline exception or suppression mechanism: fix a false
positive in the text or in the private deny-list.

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
project's repository, and its own state directory. Set
`AGENT_CYCLE_PROFILE` to the absolute path of its TOML profile; there is no
default or profile search path. The tracked examples are
`profiles/check_rst.toml` and `profiles/agent-cycle.toml`.

A version-1 profile has exactly these required keys:

| Key | Meaning |
|---|---|
| `profile_version = 1` | the profile format version |
| `name` | a non-empty label for people; no tool reads it |
| `repository` | the chat's expected working directory and the only repository where commits may be escalated |
| `state` | the directory holding the active-chat record, queue lock and pending marker |

Version 2 has the same four keys and adds a non-empty ordered array of
`[[validation]]` tables. Each table has a unique `name` and a non-empty
`arguments` array, which is executed directly without a shell. Optional
`environment` string entries augment the environment; `pytest`, `always_show`
and `require_clean` are boolean flags. The `{base}` placeholder in an argument
requires `validate.py --base REV`. A leading `~/` in an argument is expanded
against `HOME`.

The complete argument `{rst_files}` also requires `--base REV`. It expands to
the repository-relative paths whose final names end in `.rst` and whose Git
change type in `REV..HEAD` is added, copied, modified, renamed or type-changed.
For a rename, only the current path is passed; deleted paths are omitted. If
the range has no such path, the step is recorded as skipped and is not run, so
the command cannot fall back to inspecting uncommitted files. The placeholder
must occur exactly once as a complete argument. This addition does not change
the version-2 profile grammar; profiles that do not use it behave as before.

The `repository` and `state` values must be absolute or start with `~/`; the latter form is
expanded against `HOME`. Their spelling is canonical: no empty, `.` or `..`
component and no trailing slash. This check is lexical and does not access the
filesystem. Unknown or missing keys, wrong types, unsupported versions, invalid TOML
and unreadable files are configuration errors. The stateful tools refuse with
exit status 2 before writing anything. `AGENT_CYCLE_REPO`, `AGENT_CYCLE_STATE`
and `S0_STATE_DIR` are retired and must be unset.

The queue refuses an active-chat record that belongs to another repository.
A project's first chat can be identified against a chat of another project:
its settings are compared after moving that chat's repository paths to the
profile's repository, and must otherwise be identical. The identifier, queue
and audit load the same profile at startup; the log reader, snapshot, usage
report, result-schema reader and push-gate tools do not require one.

## License

GPL-3.0-only; see [LICENSE](LICENSE).
