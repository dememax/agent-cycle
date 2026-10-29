.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. Session renewal and bootstrap from durable records — agent-cycle project

#######################
Renewal and bootstrap
#######################

A long chat or session gets expensive: each tool call re-sends its whole
context (:doc:`tokens`). Renewal replaces it with a fresh one that works
from the durable records alone: the project's instructions and plan, the
record, the turn directories and the active-chat record.

****************
Cold bootstrap
****************

A cold bootstrap starts with this repository, the person's project checkouts
and their private public-content deny-list. It does not require private process
notes or an earlier agent conversation. ``cold-reader-manifest.toml`` maps
each scenario step to its authoritative files.

===============
Prerequisites
===============

Install the versions named in ``AGENTS.md`` and the repository lock files:
Python 3.14, Git, Ruff, mypy, ShellCheck, check_rst, check_formatting, Sphinx
and the pinned Node/Prettier dependencies. Install and authenticate the two
agent products for interactive use. Configure the public-content gate from an
approved revision as the README describes, but keep its deny-list outside this
public repository.

The person chooses which agent drives and which implements. They also choose
the model, reasoning effort and personality for each project and record those
values in the bootstrap record. They are not repository-wide defaults. In the
implementer's visible-chat panel, select ``Approve for me``: commits require
approval because ``.git`` is read-only inside the workspace, while the prompt,
audit and snapshots provide the scope checks. Automatic approval itself is
not a scope boundary.

=========================
First profile and state
=========================

Copy one tracked profile to a project-owned profile, then set its canonical
``repository`` and ``state`` paths and its ordered validation. Keep one
profile, visible implementer chat and state directory per served project.
Create the state directory with access limited to its owner. Export the
profile's absolute path as ``AGENT_CYCLE_PROFILE`` and keep the three retired
profile variables unset (:doc:`turn`).

Materialize the driver's tools from a commit that the other agent has already
reviewed. Export exactly ``bin/``, ``schemas/`` and ``profiles/`` from that
commit into a new version-named state directory; never copy them from a dirty
worktree. Record the full commit ID in ``REVISION``, write a sorted SHA-256
manifest for every exported regular file, verify every hash, then remove write
permission recursively. Compare a later copy with the approved commit before
advancing to it, and advance only after the tool change's review. Never modify
an existing pinned copy in place.

Schemas in the pinned copy are canonical for turns driven by that copy:
implementation and exception turns use
``schemas/implementation-result-v1.json``; review and orientation turns use
``schemas/review-result-v1.json``. Repository schemas are the versioned
sources. Historical schema directories and interim scanners outside the
repository are retired artifacts, not fallbacks or cleanup targets.

=========================
First chats and records
=========================

Choose a fixed sentinel that names the project and tells the implementer to
wait. The person opens a new visible chat on the project's repository with the
recorded settings, sends the sentinel once and does not type in the chat while
a queued turn runs. Identify it with ``bin/codex-identify-thread.py`` using the
sentinel, a time with an explicit offset and the prior log when one exists.
Exactly one readable candidate and no unreadable look-alike are required.

If renewal crosses a Codex CLI version, first review the new generated-log
shape. Then pass ``--accept-cli-version VERSION`` naming the new chat's exact
version. Outside renewal, review and re-pin compatible tools before using
``bin/codex-queue-turn.sh --reanchor-cli``. Neither operation accepts an
unreviewed version implicitly.

Write the active record only after identity, effective profile and CLI checks
pass. Send a materialized ``templates/orientation-brief.md`` as the first
queued turn and require an unchanged repository snapshot. The orientation
restates role, escalation, validation, stopping and next-work facts from
durable files.

The driver begins from its own fixed bootstrap message. Find its transcript by
that exact first message, workspace and creation time after the quiet point;
exactly one match is required. Record the transcript path in private state for
``bin/turn-usage.py``. Verify repository HEAD and status, remotes when network
is permitted, the absence of a running or pending turn, usage headroom and the
pinned hashes before driving work.

Before every turn, read the latest ``rate_limits`` entry whose ``limit_id`` is
``codex``. Use its reported ``used_percent`` and ``resets_at``; never infer a
reset from the clock or from an older entry. Compare remaining headroom with
measured similar turns and wait when it is insufficient. The complete
before-turn checklist is in :doc:`tokens`.

*************************
Why the records suffice
*************************

Automatic compaction reduces a long context, but what it carries forward
is an opaque summary that no one can review. The reviewed files are the
auditable state. A renewal is safe when everything the next turn needs is
in them, and nothing is in flight.

Each project's state directory has a generated ``STATE.md`` orientation
cache. A new agent session reads it first, then runs ``bin/state.py`` without
``--write`` and verifies the decision-relevant facts with their named source
commands. The cache makes the first join of repository, thread, usage and turn
facts convenient; it does not replace those authoritative records.

***************
When to renew
***************

- At the next quiet point, at once, when a single call or message
  exceeds 80 % of its context window, or a compaction occurs during active
  work.
- Otherwise, when two consecutive turns exceed the median threshold
  (the implementer: an upper median above 150,000 tokens per call; the
  driver: above 300,000 per message), or at the third compaction since the
  last renewal.
- A release or work-package boundary is the preferred moment to act on a
  triggered renewal, not a trigger by itself.

``bin/turn-usage.py`` records the compaction buckets, peak Codex context
pressure and both medians, then reports the immediate, consecutive-turn and
third-compaction triggers. Its ``notes`` preserve any fact that could not be
determined instead of treating it as no trigger.

*****************
The quiet point
*****************

The outgoing driver checks, with commands:

1. no implementer turn is running, and no submission is pending;
2. no runner or watcher is running;
3. every repository concerned is clean, and its remote state is checked
   with ``git ls-remote``;
4. the evidence the next turn needs is archived, with a manifest;
5. the records are current: the newest state section, the plan's next
   action, and the driver's memory.

Then it stops driving. Only one driver exists at a time.

************************
A new implementer chat
************************

1. The person opens a new chat in a VS Code window on the project's
   repository, with the same settings as the old one, and sends one fixed
   sentinel message that asks the implementer to wait.
2. The driver identifies it, fail-closed, with
   ``bin/codex-identify-thread.py SENTINEL SINCE OLD_LOG``. A candidate is
   a log that parses completely, comes from the VS Code extension, has the
   project's working directory, was created after ``SINCE``, and whose
   first message is the sentinel, in a completed turn. Exactly one
   candidate and no unreadable look-alike are required.
3. It compares the settings with the old chat's on the twelve stopping
   keys. The new chat's effective profile uses its initial ``turn_context``
   and only a ``thread_settings_applied`` event inside that initial turn. The
   old chat uses its latest context and latest settings event. Context values
   take precedence, and every stopping key must be known. The identifier
   prints each new value's source; any difference or unknown stops, and the
   driver says which setting to change.
   A project's first chat is compared with another project's chat, after
   moving that chat's repository paths to the new repository.
4. It reports both chats' ``session_meta`` CLI versions. Equal versions need
   no option. A difference fails closed, before ``--write`` can record
   anything, and tells the driver to verify the changed generated-log shape.
   After that review, the driver reruns identification with
   ``--accept-cli-version VERSION``, where ``VERSION`` must equal the new
   chat's version exactly. A missing or different value is refused. The
   successful ``--write`` records the new chat and its CLI version as the
   single active chat. The old chat is never addressed again.
5. It sends a read-only orientation turn: the implementer reads the
   instructions and the current state, and restates in its own words its
   role, the escalation rule, the protocol, the JSON contract and the next
   work item. Any contradiction it finds between the files is a finding.

**********************
A new driver session
**********************

1. The person starts it with one fixed message pointing at the
   bootstrap procedure.
2. The new session finds its own transcript uniquely: the one whose
   first message is that fixed message, created after the quiet point.
3. It verifies the state with commands, not from memory: the
   repositories and their remotes, that no turn is running, that no runner
   is left, the implementer's usage limits, and the pinned tools' hashes.
4. It reports the verified state and the next action to the person,
   then continues.

*********************
CLI version changes
*********************

Outside renewal, the queue refuses when ``codex --version`` differs from the
active record. This means the executable may emit a log shape the pinned tools
have not reviewed. The driver does not re-anchor from the refusal alone. It
first inspects generated reproductions of the new format, has the parser and
refusal changes independently reviewed, and re-pins the approved tools.

Only then does it run ``bin/codex-queue-turn.sh --reanchor-cli``. That separate
locked operation prints both versions, retains the old value with a timestamp
in ``cli_version_history``, and atomically updates the anchor. The next ordinary
queue invocation performs the version check again.
