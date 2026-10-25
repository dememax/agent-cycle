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

Fail-closed tooling for a reviewer-implementer pair of AI coding agents.
One agent drives and reviews; the other implements, one test-first
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
   review

********
Status
********

In use
   Stage S0+ (:doc:`stages`). The driver queues every turn itself; nobody
   relays messages.

Tests
   The tools' refusal paths are characterized by a pytest suite that uses
   only generated logs and a fake Codex CLI.

In progress, the first work package
   - a fail-closed parser for the audit's escalation detection (under
     review);
   - the push gate, which must pass before anything here is pushed;
   - the remaining Ruff, mypy and ShellCheck findings;
   - project profiles, replacing the two environment variables that
     select a project today.
