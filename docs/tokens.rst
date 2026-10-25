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

``bin/turn-usage.py`` writes ``usage.json`` for each turn and prints one
row:

The implementer
   The 5-hour and weekly ``used_percent`` before and after the turn (a
   drop means the window reset), the turn's input, cached and output
   tokens, and its median context per call, all from the chat's log.

The driver
   The tokens of its own messages over the cycle, from the end of the
   previous turn to the end of this one, deduplicated by message ID, and
   its median context per message, from its transcript.

A usage limit on either agent is an incident (:doc:`design`). Before
queueing, the driver compares the remaining 5-hour allowance with what
similar turns used, and waits for the reset rather than let a limit cut a
turn short.
