.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. Sanitized summary of decisions that shape the cycle — agent-cycle project

###########
Decisions
###########

This is an operational ledger, not a transcript or an exhaustive history.
It includes decisions needed to understand the current repository and marks
historical proposals that are not current procedure. Project-specific product
decisions remain with the downstream project.

``active``
   The outcome governs current S0+ work.
``conditional``
   The outcome applies only when its stated precondition holds.
``completed``
   A one-time outcome explains the current state but grants no new authority.
``superseded``
   A later decision replaced it.
``unimplemented``
   A constraint for a later stage, not behaviour of the present tools.

.. list-table:: Decision ledger
   :header-rows: 1
   :widths: 16 49 13 22

   * - ID
     - Outcome
     - Status
     - Reconsider when
   * - P1
     - Codex implements and Claude Code drives and reviews; a deliberate role
       reversal is reserved for a symmetry test.
     - active
     - The person schedules that test.
   * - P2
     - The public repository name and GPL-3.0-only licence are established;
       the proposed Python package and unified command do not exist.
     - conditional
     - A measured need justifies packaging or a unified command.
   * - P3
     - Plans and protected project material stay outside this public tooling
       repository and enter a turn only through explicit narrow scope.
     - active
     - The privacy boundary or repository visibility changes.
   * - P4
     - Later unattended stages require pinned standalone agent CLIs with path,
       version and hash; extension discovery is an S0 or emergency route.
     - unimplemented
     - S2 implementation begins.
   * - P5
     - Later controllers use bounded rounds, turn time and run time, with
       larger totals earned by clean evidence.
     - unimplemented
     - Controller work begins or operating evidence changes the bounds.
   * - P6
     - The bounded S0 trial began on a downstream project.
     - completed
     - Never; S0+ superseded its transport.
   * - P7a–P7d
     - Unattended subscription use is evidence-gated; confinement, credential
       denial and the mount policy are mandatory safety properties.
     - conditional
     - The exact confinement probe is run and reviewed.
   * - P8
     - A usage limit stops by default; bounded waiting requires explicit
       opt-in and a trustworthy near-term window reset. Never substitute an
       agent, model or login.
     - active
     - Automated-run policy or reliable limit telemetry changes.
   * - P9
     - Future automated repositories verify durable local Git settings before
       runs.
     - unimplemented
     - Index durability is proven unnecessary or controller work begins.
   * - P10
     - Supervised single-round S1b may precede the confinement probe only
       after S1a demonstrates a concrete need; unattended work still waits.
     - conditional
     - S1a evidence demonstrates that need.
   * - LOGFMT-1
     - A stopping key absent from ``turn_context`` is completed from the
       applicable ``thread_settings_applied`` event; an unknown key always
       refuses rather than comparing equal.
     - active
     - The Codex generated-log format or stopping-key set changes.
   * - CLIVER-1
     - The active-chat record anchors the Codex CLI version; ordinary queueing
       refuses a mismatch, and re-anchoring follows review as a separate act.
     - active
     - A new CLI version or log format is independently reviewed.
   * - CLIVER/M1
     - Renewal across CLI versions requires
       ``--accept-cli-version VERSION`` naming the new version exactly, after
       its generated-log shape is reviewed.
     - active
     - The identifier gains another independently reviewed compatibility
       mechanism.
   * - RUFF-17
     - The cycle's maintained repositories pin and validate with the host's
       Ruff 0.17.3 after a coordinated compatibility review.
     - active
     - A supported Ruff or host-toolchain change is proposed and reviewed.
   * - RENEWAL/D2
     - Renew immediately after active-work compaction or excessive single-call
       pressure, otherwise on the consecutive-median or third-compaction
       triggers.
     - active
     - Measurements justify different thresholds.
   * - TOKENS/D1
     - Keep one plan and use the section reader and generated state cache
       rather than parallel summaries.
     - active
     - Durable-state measurements show a correctness problem.
   * - TOKENS/D2
     - Build only the measured minimal token-saving tools before extending
       automation.
     - completed
     - New measurements demonstrate another repeated cost.
   * - REPO/D1
     - The repository is named ``agent-cycle``.
     - completed
     - A migration has a concrete benefit greater than its compatibility cost.
   * - REPO/D2
     - The repository became public only after the public-content gate existed
       and the initial range passed it.
     - completed
     - Repository visibility changes.
   * - REPO/D3
     - The repository uses GPL-3.0-only.
     - active
     - The copyright holder decides to revisit licensing.
   * - REPO/D4
     - The initial import was a person-approved one-time exception; later work
       follows the normal implementer/reviewer roles.
     - completed
     - Never; it grants no continuing exception.
   * - REPO/D5
     - Renewal preceded repository bootstrap, which then delivered profiles,
       tests, the gate and the minimal tools.
     - completed
     - Never; it records sequencing already performed.
   * - WORKSPACE/D1
     - Each served project normally has a separate chat, state directory and
       profile. A person may authorize one other repository for one exact
       turn; outside-workspace files remain read-only to ordinary commands, so
       cache-writing validation uses a fresh export.
     - active
     - A reviewed isolation mechanism replaces per-project workspaces, or an
       exception needs broader authority.
   * - PUSHGATE/D1
     - Protected patterns stay in a private deny-list outside the public
       repository, using the documented environment override when needed.
     - active
     - The privacy boundary or gate design changes.
   * - VALIDATE2/D1
     - One exact history command repaired gate-rejected unpushed commits;
       future history repair needs a new exact authorization, complete
       validation and a new publication scan.
     - completed
     - Another gate finding cannot be removed without rewriting unpublished
       history.
   * - SWITCH/D1
     - Turns use an approved pinned read-only tool copy; the former shared
       installation is retired.
     - active
     - A verified immutable installation mechanism replaces it.
   * - REL/D1
     - ``pyproject.toml`` is the version source; releases use reviewed release
       commits, annotated unsigned tags and person-owned atomic publication.
     - active
     - The release mechanism or hosting guarantees change.
   * - REL/D2
     - The first release procedure was exercised and accepted.
     - completed
     - Never; later releases use REL/D1.
   * - TAG/D1–TAG/D3
     - Earlier tag schedules and exact-command permissions are expired; every
       future tag needs a new exact authorization and publication stays human.
     - completed
     - The person authorizes a particular future tag command.
   * - A2I/D1
     - The interpretation-transparency trial was evaluated.
     - superseded
     - Never; A2I/D2 replaced it.
   * - A2I/D2
     - Every brief carries the unchanged interpretation-transparency block;
       schema enforcement waits for evidence that prompt enforcement missed.
     - active
     - A miss occurs that a schema change would have caught.
   * - COLD/D1
     - The interrupted cold-reader review resumed with exact read paths and
       produced the seven-point implementation scope.
     - completed
     - The cold-reader drift test exposes another missing authority.
