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
   keys; any difference stops, and the driver says which setting to change.
   A project's first chat is compared with another project's chat, after
   moving that chat's repository paths to the new repository.
4. It records the chat (``--write``) as the single active chat. The
   old chat is never addressed again.
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
