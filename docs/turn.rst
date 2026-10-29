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

A version-2 profile adds a non-empty ordered array of ``[[validation]]``
tables. Each table names a shell-free argument array and may declare an
environment plus the ``pytest``, ``always_show`` and ``require_clean`` flags.
``{base}`` expands inside an argument and requires ``validate.py --base REV``.
The complete argument ``{rst_files}`` likewise requires ``--base`` and expands
to the repository-relative, non-deleted ``.rst`` paths added, copied, modified,
renamed or type-changed in ``REV..HEAD``. A rename contributes its current
path. When the range contains no eligible path, that step is recorded as
skipped instead of running without file arguments. A leading ``~/`` in an
argument expands against ``HOME``. Existing version-1 and version-2 profiles
remain valid.

The driver runs the tools from a pinned, read-only copy of an approved
revision, never from the live checkout. Otherwise the implementer's
commits in this repository would change the tools that audit them. A tool
change is re-pinned only after its review.

The active-chat record also anchors the Codex CLI version from the chat's
``session_meta``. The queue asks its selected executable for ``codex --version``
before it creates turn evidence or a pending marker. A missing anchor,
unparseable output or a different version is a refusal, not an implicit
upgrade.

*************************
Operational environment
*************************

The tools have a deliberately small environment contract:

``AGENT_CYCLE_PROFILE``
   Required absolute path of the selected project profile.
``AUDIT_EXTRA_ALLOW``
   Optional regular expression for one person-authorized exact-command
   exception. It is absent in ordinary turns; the exception procedure below
   governs its use.
``CODEX``
   Optional path to the Codex executable. Without it the queue resolves the
   executable associated with the visible VS Code integration.
``S0_QUEUE_TIMEOUT``
   Optional queue submission and observation timeout in seconds; the default
   is 300.
``HOME``
   Required when a profile or validation argument begins with ``~/`` and used
   by the repository snapshot to locate the configured workspace hierarchy.
``TMPDIR``
   Optional parent for the snapshot tool's temporary output; the default is
   ``/tmp``.

``AGENT_CYCLE_REPO``, ``AGENT_CYCLE_STATE`` and ``S0_STATE_DIR`` are retired.
They must be unset; their presence is a configuration error. The public gate's
separate ``AGENT_CYCLE_DENY_LIST`` contract is documented in the README.

********************
The brief contract
********************

Every prompt records status, context, the complete work item, rules and the
final-message contract. It names the base, read and write scope, permitted
escalations, expected RED failures, validation, stop conditions and the
selected schema from the approved pinned tool copy. A list entry that is
evidence is identified by its exact spelling or line range, not by a pattern
that might select an older similarly formatted entry.

The reusable sources are:

- ``templates/implementation-brief.md`` for a writing turn;
- ``templates/review-brief.md`` for an independent read-only review;
- ``templates/orientation-brief.md`` for the first turn in a new chat; and
- ``templates/exact-exception-brief.md`` when the person has authorized one
  complete command outside the ordinary allowlist.

The files carry repository copyright comments. When materializing
``prompt.md``, copy from the ``[S0 DRIVER: ...]`` marker, substitute every
angle-bracket placeholder and remove no required section. Implementation and
exact-exception prompts select
``schemas/implementation-result-v1.json`` from the pinned copy; review and
orientation prompts select ``schemas/review-result-v1.json`` there.

Every brief ends with the exact contents of ``templates/a2i-block.md``. Do not
paraphrase that block: it makes assumptions, interpretations, deviations and
brief defects part of the result contract. Project-specific facts belong in a
materialized prompt, never in the reusable template.

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
- the latest effective profile equals the recorded profile on the twelve
  stopping keys (working directory, approvals, sandbox, permissions, model,
  effort, collaboration mode, personality and the rest);
- the executable's CLI version equals the active record's anchor;
- ``prompt.md`` starts with the driver header.

An effective profile starts with a ``turn_context``. A stopping key present
there always wins. An absent key is completed from
``thread_settings_applied``: ``runtime_workspace_roots`` supplies
``workspace_roots``, ``reasoning_effort`` supplies ``effort``, and the other
names are unchanged. For the queue, the latest context uses the latest
settings event anywhere in the log. A value found in neither source is
unknown and always refuses; two unknowns never compare equal. A stored
baseline with a missing or null stopping key is malformed and also refuses.

It reads ``prompt.md`` once, under the lock, and uses that text for
validation, submission and comparison. It writes ``pending.json`` durably,
submits, and polls the log until exactly one new turn carries that text.
Only then does it write ``turn-id`` and remove the marker. A second new
turn, a foreign prompt, a malformed line, a failed submission or a timeout
refuses, and keeps the marker. Every later call then refuses until a
person investigates.

After an independently reviewed CLI log-format change, the driver may advance
the active record's anchor explicitly::

   bin/codex-queue-turn.sh --reanchor-cli

The command takes the same queue lock, validates the active log and effective
profile, prints the old and new versions, appends the old value and a timestamp
to ``cli_version_history``, and atomically writes the record. It refuses when a
turn is running, a submission is pending, the profile is unknown or changed,
or the executable is already at the recorded version. An ordinary queue call
never re-anchors.

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
   Save its standard output in ``audit.txt``, then append ``audit exit N``
   with the command's exit status; the record generator never infers it.
   Commands are tokenized as shell syntax; other operators, redirections and
   expansions are flagged, and ``git commit --amend`` needs the turn's exact
   authorization.
3. Require ``bin/github-snapshot.sh`` to exit zero, then compare
   ``snapshot-after.txt`` with ``snapshot-before.txt``. Only the project's
   HEAD and status may have changed. The extension's ``refs/codex/`` turn
   checkpoints are counted separately.
4. Any non-zero audit or snapshot, or any unexpected snapshot change, is an
   incident. Stop and tell the person. The driver may establish the facts
   first, for example that a flagged call only wrote a test fixture, but the
   person decides how work resumes.
5. Run ``bin/validate.py --base BASE`` with the project's selected profile;
   it runs every declared check once and retains each check's raw output.
   Review the result by reproducing it (:doc:`review`).
6. Usage: ``bin/turn-usage.py CLAUDE_TRANSCRIPT --previous
   PREVIOUS_TURN_DIR TURN_DIR`` writes ``usage.json`` only into ``TURN_DIR``
   and prints its table row and renewal facts. ``PREVIOUS_TURN_DIR`` is
   read-only; its end is where the driver's cycle for the current turn
   begins. Without ``--previous``, that window starts at ``TURN_DIR``'s
   ``started`` time (:doc:`tokens`).
7. Start the turn record with ``bin/turn-record.py TURN_DIR`` after all the
   evidence above exists, then add the review's judgement, findings and
   verdict to its factual Markdown skeleton.
8. After the turn record is complete, run ``bin/state.py --write`` to
   regenerate ``STATE.json`` and ``STATE.md`` in the selected project's state
   directory. The next restart reads the Markdown cache first, but verifies
   its decision-relevant facts by command.

**************************
Exact-command exceptions
**************************

The ordinary escalation policy remains ``git add`` and ``git commit`` in the
profile's repository. An exception exists only when the person authorizes one
complete command for one named turn. Before queueing it, the driver:

1. materializes ``templates/exact-exception-brief.md`` with the exact command,
   workdir, reason and no-retry rule;
2. computes ``AUDIT_EXTRA_ALLOW`` as a start-to-end full match of
   ``re.escape(command)``;
3. probes the expression against the exact command and negative cases,
   including changed options, workdir, spelling, chaining, repetition and a
   different repository; and
4. keeps the expression, probes and results in the turn directory.

The audit still parses the command as shell syntax and applies all of its
safety checks. ``AUDIT_EXTRA_ALLOW`` extends only the final command allowlist;
it never makes redirection, expansion or an ambiguous call safe. The audit's
small shell grammar accepts a chain only when every part is independently
allowed, but an exact-command exception must be invoked alone; its negative
probes enforce that narrower prompt rule. Run the authorized command at most
once. If it fails, do not improvise or retry: stop and report the error.
Afterward, run the audit both with the exact extension and, as useful
evidence, without it to show that the base guard still rejects the exceptional
command.

An exception for another repository changes only the repository named by that
turn. Ordinary commands from the original chat may find that repository
read-only because it is outside the chat's workspace. Validation that writes
caches therefore runs on a fresh export under ``/tmp`` when the brief permits
it; the exception does not widen the workspace or authorize another project.

*******************
Incident handling
*******************

S0+ uses a conservative rule: any usage limit, power loss, audit anomaly,
snapshot anomaly, gate finding or unexpected repository state stops the work.
The driver preserves the evidence, establishes only the facts needed to name
the incident, notifies the person and waits for an explicit resumption
decision. It never substitutes another agent, model or login, and never
silently retries an effectful turn.

If an implementation turn is known to have been cut short, first record HEAD
and the worktree status. A person-authorized continuation is a new linked turn
that states the interruption and observed state; it does not pretend the old
turn completed. A cut read-only review has no candidate changes to preserve,
so discard its partial conclusion and start a fresh review.

After a power loss, inspect the active log for in-flight turns, the pending
marker and queue lock, repository HEAD and status, snapshots, runners and the
last durable turn record. Delete or repair nothing merely because it looks
stale. Report the inspection and wait for the person before resuming.

When the public-content gate finds protected material in unpushed commits,
stop. Adding a later commit does not remove an earlier offending blob from the
range. If repair therefore requires rewriting unpublished history, the person
must authorize the exact history command for one turn; use the exception
procedure above and re-run both validation and the complete publication scan.

Later controller stages may assign typed exit codes, durable journals,
automatic notifications and explicit ``resume`` or ``abandon`` commands.
Those behaviours are design constraints, not features implemented by the
current S0+ scripts; :doc:`stages` marks their status.

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
     - the audit's standard output followed by ``audit exit N``, and the final
       message; ``result.json`` only when the complete message parses as one
       JSON object
   * - ``usage.json``, ``usage-row.txt``
     - both agents' usage and the renewal facts for the turn
