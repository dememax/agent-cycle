.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. What costs tokens, and how the cycle saves them — agent-cycle project

###############
Token economy
###############

*******************
What costs tokens
*******************

- Each tool call re-sends the whole context, mostly as cached input.
  A turn's cost is roughly *calls × context size*, not the size of the
  prompt or of the files written.
- A file read into the context stays there. A large file read early
  is re-sent with every later call of the turn, and for the implementer it
  stays in the chat until a compaction. Reading narrowly matters more than
  writing tersely.
- Bytes are cheap; separate calls are not. A long text costs little to
  write, but every separate write, edit or poll is another call.

********************
Habits that follow
********************

- Read large documents in parts: list the headings, then read the one
  section needed.
- Batch coherent edits into one call where that is safe, and do not
  read back a file just written.
- Launch long jobs once, detached, with a completion marker and compact
  output (counts, and failures only), rather than polling them call by
  call. A detached job also survives a usage limit that ends the turn.
- Keep reports bounded. The final message's report states results and
  points to evidence by path; the reviewer opens the evidence only when it
  needs to.
- Renew a chat or session when its context per call grows past the
  thresholds of :doc:`renewal`.

***********
Measuring
***********

``bin/turn-usage.py CLAUDE_TRANSCRIPT [--previous PREVIOUS_TURN_DIR]
TURN_DIR`` writes ``usage.json`` only for ``TURN_DIR``. The optional previous
turn is read-only. It prints the existing table row followed by one
``renewal:`` line:

The implementer
   The 5-hour and weekly ``used_percent`` before and after the turn (a
   drop means the window reset), the turn's input, cached and output
   tokens, and its median context per call, all from the chat's log.

The driver
   The tokens of its own messages over the cycle, from the end of the
   previous turn to the end of this one, deduplicated by message ID, and its
   median context per message, from its transcript. Without ``--previous``,
   the window begins at this turn's ``started`` time. ``usage.json`` records
   which source was used.

Renewal
   Compaction line numbers inside the turn, between turns and across the
   thread; the largest per-call Codex input, the latest context window and
   their percentage; both medians; and the resulting renewal triggers. The
   consecutive-median rules read the previous turn's ``usage.json``. A fact
   that cannot be established is ``null`` and is explained in ``notes``;
   unknown evidence is never reported as an empty trigger condition.

A usage limit on either agent is an incident (:doc:`design`). Before
queueing, the driver compares the remaining 5-hour allowance with what
similar turns used, and waits for the reset rather than let a limit cut a
turn short.

***********************
Before-turn checklist
***********************

Before queueing, the driver:

1. reads the latest rollout ``rate_limits`` entry whose ``limit_id`` is
   ``codex``;
2. records that entry's ``used_percent`` and ``resets_at`` exactly as
   reported, treating a missing fact as unknown;
3. never infers that a reset occurred from wall-clock time, an older entry or
   a projected schedule;
4. compares the remaining 5-hour headroom with the measured consumption of
   similar completed turns; and
5. waits for a reported reset instead of queueing work whose expected cost
   does not fit.

This preflight is a scheduling guard, not a promise that the next turn will
fit. A limit reached despite it follows the incident procedure in
:doc:`turn`; roles, models and logins are not substituted.
