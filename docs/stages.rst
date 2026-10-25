.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. Stages of automation and the gate between them — agent-cycle project

########
Stages
########

The process is observed first, then automated, one stage at a time. Only
S0 and S0+ have run; the later stages are designed, not built.

.. list-table::
   :header-rows: 1
   :widths: 10 60 30

   * - Stage
     - Content
     - State
   * - S0
     - A supervised trial. The driver relays each turn to a forked
       implementer session through the CLI, with schema-validated results.
     - run; superseded by S0+
   * - S0+
     - The visible chat. The driver queues each turn into the
       implementer's visible chat, where the person can watch it, and
       audits it afterwards (:doc:`turn`). Nobody relays messages.
     - in use
   * - S1a
     - The evidence gate. The driver summarizes the record of S0, the
       implementer reviews the summary, and the person decides whether to
       stay or to build the next stage.
     - decided: stay with S0
   * - S1b
     - A supervised minimal ``once``: one round driven by a local
       controller, with the mechanical RED/GREEN gate in a disposable
       clone, the reviewer in its own clone, and a minimal journal. Every
       outcome other than approval stops.
     - designed
   * - S2
     - The hardened controller: enforced confinement of the agents,
       transactional turns, a full journal and an explicit ``resume``. A
       passed confinement probe is its precondition.
     - designed
   * - S3
     - The plan-revision, checkpoint and decision flows, and a findings
       ledger.
     - designed
   * - S4
     - ``run``, unattended, with budgets and typed stops. Requires S2.
     - designed
   * - S5
     - Adapters for SDKs and app servers.
     - designed

*************************
The gate between stages
*************************

A stage is built only when the record of the stage in use shows a concrete
need that the next one removes: relay actions that remain, or reliability
problems. Supervision is not confinement: a stage that runs unattended
needs the confinement probe first. Every outcome of a gate is the person's
decision, recorded in the project's plan.

************
The record
************

While a stage runs, the driver keeps a record, one entry per turn or work
item: what was asked, the commits, the audit and the snapshots, the
findings, the incidents and their outcome, the elapsed time, and the usage
of both agents. The gate decides from that record, not from memory.
