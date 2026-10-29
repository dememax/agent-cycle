<!--
Copyright (C) 2026 Maxime P. DEMENTYEV
SPDX-License-Identifier: GPL-3.0-only
Review-turn brief template — agent-cycle project
-->

[S0 DRIVER: <driver>] <project> review turn <turn>: **<work-item>.**

**1. Status.** Name the candidate and its verified base `<base>`. State
which earlier verdicts, findings and user decisions remain in force.

**2. Context.** Explain the review question and the claims that require
independent reproduction. The candidate in `<repository>` is read-only.

**3. Work item.** List the exact files, commits, tests and probes to review.
Require evidence for every finding and distinguish a defect from a guard's
documented scope limit.

**4. Rules.** This is read-only: no file mutation, commit or escalation.
Name the complete read scope. Stop on an incident, and use `needs_user` for
a blocker or a decision reserved to the person.

**5. Final message.** Return exactly one JSON object matching
`<pinned-tools>/schemas/review-result-v1.json`, with `reviewed`
`<work-item>`. Mention `<base>`, the reproduced evidence and unresolved
questions in the report.

**Interpretation transparency (`A2I/D2`, permanent; adapted from the user's a2i rules 42, 58 and 59).** Only where relevant; short entries; "none" is a valid answer.
- End `report` with three headed lists:
  - **Assumptions:** what you assumed because the brief or the files were missing, ambiguous or underspecified.
  - **Interpretations chosen:** where an instruction allowed more than one reading, which one you chose and why.
  - **Deviations from the brief:** every place where you treated an instruction as a preference rather than a hard rule, or did something other than what it says, with the reason.
- **Check the brief itself:** a factual error, a hidden assumption, a contradiction with the files, or a prescribed fix that does not serve the stated goal. Name it with the brief's own wording (in a review turn, as a `findings` entry; in an implementation turn, at the top of the Assumptions list). If it blocks the work, stop as the rules say.
- **Scope and certainty:** for each claim in `report`, say whether you verified it (by which command) or assume it; when something is uncertain, name the cause (missing context, underspecified brief, or out of scope). Qualitative words only, no probabilities.
- When two readings remain equally plausible and the choice matters, do not pick silently: ask in `needs_user` (or `decisions_requested`), with the smallest fact that would decide it.
