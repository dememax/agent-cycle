.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. Terms used by the supervised cycle — agent-cycle project

##########
Glossary
##########

The terms below describe the defensive, auditable and supervised procedure.
They do not imply that its guards are a security boundary.

.. glossary::

   AGENTS.md
      The contributor instructions and single source of development-tool
      versions for this repository.

   AGENT_CYCLE_PROFILE
      The environment variable whose value selects the one explicit project
      profile used by stateful cycle tools.

   active-thread record
      The project's record of its one active implementer chat, stored as
      ``active-codex-thread.json`` in the run state with the chat's sentinel
      and profile baseline.

   brief
      The complete prompt for one bounded turn. It records the work item,
      authority, evidence, validation, stop conditions and selected final-
      message contract.

   cold bootstrap
      Reconstruction of the working procedure from versioned repository files
      and project-owned records, without relying on an earlier agent
      conversation. See :doc:`renewal`.

   cold-reader-manifest.toml
      The versioned map from each complete cold-reader scenario step to its
      authoritative files.

   compaction
      An automatic reduction of the chat context. The recovery and stopping
      rule is ``COMPACTION/D1`` in the :doc:`decisions`.

   decision ledger
      The operational table in :doc:`decisions` that records the outcomes
      needed to understand the current procedure and their status.

   driver
      The agent that prepares and queues a turn, audits its execution and
      reviews the implementer's result. The person chooses which agent has
      this role.

   implementer
      The agent that performs one bounded work item, commits only within the
      authority of its turn and returns the selected result contract.

   pinned tool copy
      A read-only export of reviewed ``bin/``, ``schemas/`` and ``profiles/``
      content from one recorded commit. It is the driver's executable and
      contract source for a turn.

   profile baseline
      The active-thread record's stored values for every stopping key,
      including the working directory, approvals, sandbox, permissions,
      model, effort and collaboration mode. Queueing compares the latest
      effective profile with this baseline.

   public-content gate
      The pre-push check that refuses configured protected patterns in content
      and metadata. It supplements review; it is not a sandbox and cannot
      establish that content is public.

   RED and GREEN
      The test-first pair for one behavioral correction. RED records the
      smallest intended failing predicate; GREEN supplies the minimal coherent
      implementation that makes it pass.

   run state
      Project-specific active-chat, turn and evidence data stored outside this
      public repository under the person's selected state directory.

   sentinel
      The fixed first message that identifies an implementer chat. The
      active-thread record preserves it, and the queue requires the chat's
      initial completed turn to contain the same message.

   schemas/implementation-result-v1.json
      The versioned final-message contract for implementation and exact-
      exception turns.

   templates/
      The versioned material sources for orientation, implementation, review
      and exact-exception briefs.

   turn
      One queued, bounded unit of implementer work followed by audit, snapshot
      comparison and independent review.

   bin/audit-turn.py
      The tool that enumerates escalations, extracts the final JSON object and
      validates it against the selected schema after a turn.

   bin/validate.py
      The tool that executes a profile's ordered validation steps once and
      retains their raw output.

   WORKSPACE/D1
      The active decision requiring separate project chats, profiles and state
      directories, with broader access limited to an exact one-turn exception.
