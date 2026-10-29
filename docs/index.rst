.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. Sphinx documentation root — agent-cycle project

#############
agent-cycle
#############

:Project: |project|
:Author: |author|
:Copyright: |copyright|
:Language: English

Tooling for a reviewer-implementer pair of AI coding agents, whose guards
fail closed. One agent drives and reviews; the other implements, one test-first
RED/GREEN pair at a time; a person decides everything that is theirs.
Today the driver is Claude Code and the implementer is Codex, in its
visible VS Code chat. The driver queues each turn into that chat, audits
the commands the implementer escalated, snapshots the repositories, and
reviews the commits by reproducing them.

The process is project-agnostic. Each project has its own implementer
chat, opened on that project's repository, and its own state directory.
The first project served is `check_rst <https://github.com/dememax/check_rst>`_;
the second is this repository itself.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   design
   stages
   turn
   renewal
   tokens
   glossary
   review
   decisions
   releasing

********
Status
********

Release
   Version |release|; the second work package and token tools are complete.

In use
   Stage S0+ (:doc:`stages`). The driver queues every turn itself; nobody
   relays messages.

Tests
   The tools' refusal paths are characterized by a pytest suite that uses
   only generated logs and a fake Codex CLI.

Done in the first work package
   The tests; the audit's fail-closed escalation parser and complete result
   validation; the public-content push gate; fail-closed repository
   snapshots; usage and renewal facts; the initial lint debt; and project
   profiles.

Done in the second work package
   Shell-aware escalation auditing, refusal of unreadable usage inputs, the
   section reader, turn-record generator, profile-driven validation runner and
   generated state cache.

*************************
Authoritative locations
*************************

The versioned sources are ``bin/`` for cycle tools, ``tools/`` for the
public-content gate and installer, ``schemas/`` for result contracts,
``profiles/`` for tracked profile examples, ``templates/`` for brief sources,
and this documentation for procedure. ``cold-reader-manifest.toml`` maps the
complete cold-reader scenario to those authorities.

A running driver uses an approved pinned read-only copy of ``bin/``,
``schemas/`` and ``profiles/`` as :doc:`renewal` describes. The selected
schema comes from that copy, so it stays aligned with the tool performing the
audit. Old shared tool installations, external schema copies and interim
scanners are retired historical artifacts. They are not fallbacks, and this
repository procedure neither consumes nor deletes them.
