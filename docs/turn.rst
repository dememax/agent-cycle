.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. The procedure for one turn — agent-cycle project

##########
One turn
##########

A turn is one prompt to the implementer and everything the driver does
around it. Each turn has its own directory, ``turn-NNN/``, in the
project's state directory. One chat's turn runs at a time.

***********************
Selecting the project
***********************

The queue, identifier and audit require ``AGENT_CYCLE_PROFILE`` to be the
absolute path of a TOML profile. There is no default and no profile search.
The tracked ``profiles/check_rst.toml`` and ``profiles/agent-cycle.toml``
files are examples. A version-1 profile has exactly four required keys:

- ``profile_version = 1``;
- ``name``, a non-empty label for people, which no tool reads;
- ``repository``, the chat's expected working directory and the only one
  where commits may be escalated;
- ``state``, the directory holding the active-chat record, queue lock and
  pending marker.

The path values are absolute or begin with ``~/``, which is expanded against
``HOME``. Their spelling has no empty, ``.`` or ``..`` component and no
trailing slash. This validation is lexical and does not access the filesystem.
Invalid, unreadable or incomplete profiles and unknown keys are configuration
errors: the tool exits 2 before writing anything. The snapshot and usage
report do not load a profile.

The driver runs the tools from a pinned, read-only copy of an approved
revision, never from the live checkout. Otherwise the implementer's
commits in this repository would change the tools that audit them. A tool
change is re-pinned only after its review.

*****************
Before the turn
*****************

1. Record the pre-state: HEAD and the count of dirty entries of each
   repository concerned.
2. Take ``snapshot-before.txt`` with ``bin/github-snapshot.sh``. A non-zero
   exit is an incident; do not queue the turn from an incomplete snapshot.
3. Write ``prompt.md``. It begins with the driver header
   ``[S0 DRIVER: Claude Code]``, which the queue requires, and holds:

   - the verdict on the previous turn, with what the driver reproduced;
   - the work item and its requirement;
   - the escalation rule and the stop conditions;
   - the schema the final message must match, with the fields to fill.

**********
Queueing
**********

``bin/codex-queue-turn.sh TURN_DIR`` is the only way to send a turn. It
takes an exclusive lock and refuses unless:

- the active-chat record exists, and its log parses completely;
- the log's session metadata (identifier, source, originator, working
  directory, creation time) equals the record's;
- the chat's first message is the recorded sentinel, in a completed turn;
- no turn is running, and no earlier submission is pending;
- the latest settings equal the recorded profile on the twelve stopping
  keys (working directory, approvals, sandbox, permissions, model, effort,
  collaboration mode, personality and the rest);
- ``prompt.md`` starts with the driver header.

It reads ``prompt.md`` once, under the lock, and uses that text for
validation, submission and comparison. It writes ``pending.json`` durably,
submits, and polls the log until exactly one new turn carries that text.
Only then does it write ``turn-id`` and remove the marker. A second new
turn, a foreign prompt, a malformed line, a failed submission or a timeout
refuses, and keeps the marker. Every later call then refuses until a
person investigates.

****************
After the turn
****************

1. Wait until the log shows the turn's ``task_complete``. Watch for
   the usage limits while waiting.
2. Audit: ``bin/audit-turn.py THREAD_LOG START_LINE SCHEMA TURN_DIR``.
   Its exit status is a set of bits: 1 for an escalation outside the
   allowlist, or one it cannot parse unambiguously within its scope
   (:doc:`design`, Guards); 2 for a final message that is not exactly one
   strict JSON object, whose object fails recursive schema validation, or
   whose schema uses an unsupported keyword (:doc:`design`, Contracts); 4
   for a turn that ended on an error, such as a usage limit. It always
   writes ``final-reply.md``, and ``result.json`` only when the complete
   message parses as one JSON object.
3. Require ``bin/github-snapshot.sh`` to exit zero, then compare
   ``snapshot-after.txt`` with ``snapshot-before.txt``. Only the project's
   HEAD and status may have changed. The extension's ``refs/codex/`` turn
   checkpoints are counted separately.
4. Any non-zero audit or snapshot, or any unexpected snapshot change, is an
   incident. Stop and tell the person. The driver may establish the facts
   first, for example that a flagged call only wrote a test fixture, but the
   person decides how work resumes.
5. Review the result by reproducing it (:doc:`review`).
6. Record the turn: times, commits, audit, snapshots, the review's
   findings and verdict.
7. Usage: ``bin/turn-usage.py CLAUDE_TRANSCRIPT --previous
   PREVIOUS_TURN_DIR TURN_DIR`` writes ``usage.json`` only into ``TURN_DIR``
   and prints its table row and renewal facts. ``PREVIOUS_TURN_DIR`` is
   read-only; its end is where the driver's cycle for the current turn
   begins. Without ``--previous``, that window starts at ``TURN_DIR``'s
   ``started`` time (:doc:`tokens`).

********************
The turn directory
********************

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - File
     - Content
   * - ``pre-state.txt``, ``snapshot-before.txt``, ``snapshot-after.txt``
     - repository state around the turn
   * - ``prompt.md``
     - the prompt, as submitted
   * - ``thread-log-path``, ``thread-log-lines-before``, ``started``
     - where the turn's records begin, and when it was sent
   * - ``stdout.txt``, ``stderr.txt``, ``turn-id``
     - the submission's output and the identifier of the started turn
   * - ``finished``
     - when the turn completed
   * - ``audit.txt``, ``final-reply.md``, ``result.json``
     - the audit and the final message; ``result.json`` only when the
       complete message parses as one JSON object
   * - ``usage.json``, ``usage-row.txt``
     - both agents' usage and the renewal facts for the turn
