<!--
Copyright (C) 2026 Maxime P. DEMENTYEV
SPDX-License-Identifier: GPL-3.0-only
Implementation-turn brief template — agent-cycle project
-->

[S0 DRIVER: <driver>] <project> turn <turn>: **<work-item>.**

**1. Status.** State the reviewed outcome of the previous turn and the
verified starting commit `<base>`. Stop if `<repository>` is not at that
commit or its expected status differs.

**2. Context.** Give only the durable facts needed to understand why this
work is next. Distinguish verified facts from proposals and decisions.

**3. Work item.** State the complete acceptance criteria, the RED/GREEN
pair or reason no RED applies, and the validation and publication-content
checks. Name exact test nodes and expected failure kinds when known.

**4. Rules.** Limit reads and writes explicitly. Unless this brief says
otherwise, escalation is only `git add` and `git commit`, in `<repository>`;
there is no amend, history operation, tag, push, fetch, clone or network.
Commit messages use a file and the required co-author trailer. Stop on an
incident; request the person's decision for scope, priority or release.

**5. Final message.** Return exactly one JSON object matching
`<pinned-tools>/schemas/implementation-result-v1.json`. Use work item
`<work-item>`, base `<base>`, and report the commits, RED evidence,
validation, omissions and the three interpretation-transparency lists.

**Interpretation transparency (`A2I/D2`, permanent; adapted from the user's a2i rules 42, 58 and 59).** Only where relevant; short entries; "none" is a valid answer.
- End `report` with three headed lists:
  - **Assumptions:** what you assumed because the brief or the files were missing, ambiguous or underspecified.
  - **Interpretations chosen:** where an instruction allowed more than one reading, which one you chose and why.
  - **Deviations from the brief:** every place where you treated an instruction as a preference rather than a hard rule, or did something other than what it says, with the reason.
- **Check the brief itself:** a factual error, a hidden assumption, a contradiction with the files, or a prescribed fix that does not serve the stated goal. Name it with the brief's own wording (in a review turn, as a `findings` entry; in an implementation turn, at the top of the Assumptions list). If it blocks the work, stop as the rules say.
- **Scope and certainty:** for each claim in `report`, say whether you verified it (by which command) or assume it; when something is uncertain, name the cause (missing context, underspecified brief, or out of scope). Qualitative words only, no probabilities.
- When two readings remain equally plausible and the choice matters, do not pick silently: ask in `needs_user` (or `decisions_requested`), with the smallest fact that would decide it.
