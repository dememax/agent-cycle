.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. Roles, principles, contracts and guards — agent-cycle project

########
Design
########

*******
Roles
*******

The driver
   Writes each turn's prompt, queues it, audits the turn, and reviews the
   result. It also writes the project's plan and the design-level
   documents, which the implementer reviews.

The implementer
   Does the work item: one RED/GREEN pair, or a review of the driver's
   text. It commits locally and reports in a fixed JSON contract.

The person
   Owns every decision: scope, priority, releases, publication, and the
   reaction to any incident. The agents present options and a
   recommendation; they never settle these themselves.

Which agent takes which role is the project's decision. Today Claude Code
drives and Codex implements.

************
Principles
************

1. Files and Git are authoritative. What an agent reports is a list of
   claims to verify, never state. A final message is one JSON object that
   validates against its schema, or it is rejected.
2. No conclusion on its author's word. The implementer's commits are
   reviewed by the driver, and the driver's plans and verdicts by the
   implementer.
3. One writer per artifact. Only the implementer commits in a turn;
   only the driver writes the plan.
4. Nothing irreversible is automated. No push, tag, release or
   publication happens without the person's explicit decision for that
   occasion.
5. Fail closed. A tool that meets a malformed log line, an ambiguous
   candidate, a running turn, a pending submission or a settings mismatch
   stops with a message. It never guesses.
6. No incident is silent. A usage limit, a power loss, or an audit or
   snapshot anomaly stops the work. The driver reports what it verified,
   and work resumes only on the person's word.
7. Automation earns its next stage. A stage is built only when the
   recorded evidence of the previous one shows a need (:doc:`stages`).

***********
Contracts
***********

Every turn ends with exactly one JSON object, and nothing around it.

- ``schemas/implementation-result-v1.json``, for a work turn:

  - ``status``: ``ready_for_review``, ``blocked`` or ``needs_user``;
  - the work item, the plan revision and the base commit;
  - every commit, with its role (``red``, ``green`` or ``single``);
  - for a RED, the runner and the exact test node IDs expected to fail;
  - whether behaviour changed, and whether the GREEN edited its RED's
    assertions;
  - the validation claimed, and a report.

- ``schemas/review-result-v1.json``, for a review turn: a ``verdict``
  (``approved``, ``changes_requested`` or ``needs_user``), what was
  reviewed, the findings with severity and evidence, the questions for
  the person, and a report.

A review turn has no ``blocked``: its stop is ``needs_user`` with a
``blocker`` finding that names the condition.

********
Guards
********

The implementer works in its chat's sandbox: its repository is writable,
``.git`` is read-only, and there is no network. Committing therefore needs
an escalation, which the chat's automatic approval grants without a click.
That approval is not a scope guard, and an approved escalation runs
outside the sandbox, with the network. The guards are therefore what they
are, not a sandbox:

1. The prompt allows escalating only ``git add`` and ``git commit``,
   with the project's repository as the working directory. Anything else
   means stop.
2. The audit (``bin/audit-turn.py``) lists every escalated command
   after the turn and exits non-zero on any command outside the
   allowlist, or on an invalid final message.
3. Snapshots of every repository, before and after the turn
   (``bin/github-snapshot.sh``), including the remote-tracking refs, so
   that a push or a change to another repository shows.
4. On the hosting side, a branch ruleset that blocks force pushes and
   deletion of the main branch. It does not block an ordinary push.

A violation is found after the fact, not prevented. Against an ordinary
push, the protection is the implementer's instructions, the audit, the
snapshots and the reviewer's judgment.

*******************
Where state lives
*******************

The repository holds the tools, the schemas and these documents, never a
project's work or history. Run state stays in
``~/.local/state/agent-cycle/<project>/``: the active-chat record, the
queue lock, one directory per turn, and the evidence that later turns or
reviews need. A project's plans and records stay with that project.
