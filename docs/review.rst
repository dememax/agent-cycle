.. Copyright (C) 2026 Maxime P. DEMENTYEV
.. SPDX-License-Identifier: GPL-3.0-only
.. Review practices for either agent — agent-cycle project

##################
Review practices
##################

These hold for whichever agent reviews: the driver reviewing commits, or
the implementer reviewing the driver's plans and documents.

*************************
Reproduce, do not trust
*************************

1. A report is a list of claims to check. Run the tests, read the diff,
   probe the tool.
2. Work in your own clone at the exact candidate, never in the author's
   tree. When HEAD moves during a review, compare trees before carrying a
   verdict over.
3. Check each RED: it fails at the declared tests, as an assertion, for
   the intended reason. A GREEN that edits its RED's assertions must say
   so.
4. Check commit messages against the diff, including the trailer and
   the author identity. A false claim in a message is a finding.
5. Validate your own fixtures before reporting from them. An invalid
   input makes a false finding.

************************
Probe beyond the tests
************************

1. Probe edge cases the tests did not anticipate, from the input's own
   grammar. A parser that skips string literals must also know where a
   string cannot begin: a regular expression literal containing a quote or
   a backtick is the classic trap.
2. When a guard changes, run the old and the new version over every
   recorded turn and compare. A guard must keep every verdict that was
   right, and a guard that flags ordinary work is as unusable as one that
   misses violations.
3. Follow a merge or a simplification through every later operation.
   A merge is harmless only if nothing later depends on the distinctions it
   removed.

********
Report
********

1. Rank findings: blockers, minor findings, notes. Give each deferred
   item a target.
2. Give each finding evidence the author can reproduce: a command, a
   generated probe, a count.
3. Own your mistakes in a brief. When a finding comes from your own
   instructions, say so, and correct the requirement.
4. Raise ``needs_user`` for scope, release and priority questions,
   with the options and a recommendation. Never settle them yourself.
5. Never call your own work approved. Say "the last reported blocker
   is fixed; ready for approval review" until the other agent confirms.
6. A checkpoint checks requirements, not summaries: go through the
   requirements line by line, and name the evidence that proves each one.

***************************
What evidence may contain
***************************

The repository and its records are public. Evidence cites counts, commit
IDs, finding IDs and generated reproductions, never the content, paths or
names of private material that a project's own work touched.
