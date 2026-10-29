<!--
Copyright (C) 2026 Maxime P. DEMENTYEV
SPDX-License-Identifier: GPL-3.0-only
Exact-command exception brief template — agent-cycle project
-->

[S0 DRIVER: <driver>] <project> turn <turn>: **<work-item>, with one exact
exception.**

**1. Status.** State the reviewed reason that ordinary `git add` and
`git commit` are insufficient. Verify `<repository>` at `<base>` before
using the exception.

**2. Context.** Record the person's explicit authorization for this turn,
why the command is necessary, and why its effects are bounded.

**3. Work item.** The sole additional escalated command is `<exact-command>`.
Run it at most once and do not retry a failure. Before queueing, set
`AUDIT_EXTRA_ALLOW` to the full-match regular expression produced by
`'^' + re.escape('<exact-command>') + '$'`. Retain the expression and
negative probes in the turn directory. Probes must reject a changed workdir,
options, command spelling, chaining, repetition and another repository.

**4. Rules.** The exception authorizes only the complete command above in
`<repository>` for this turn; it authorizes no network or implicit follow-up.
It never disables the audit's shell-safety checks. All ordinary escalation
and stop rules still apply.

**5. Final message.** Return exactly one JSON object matching
`<pinned-tools>/schemas/implementation-result-v1.json`, for `<work-item>`
at `<base>`. Report whether the exception ran, its exact result, audit
evidence and all validation.

**Interpretation transparency (`A2I/D2`, permanent; adapted from the user's a2i rules 42, 58 and 59).** Only where relevant; short entries; "none" is a valid answer.
- End `report` with three headed lists:
  - **Assumptions:** what you assumed because the brief or the files were missing, ambiguous or underspecified.
  - **Interpretations chosen:** where an instruction allowed more than one reading, which one you chose and why.
  - **Deviations from the brief:** every place where you treated an instruction as a preference rather than a hard rule, or did something other than what it says, with the reason.
- **Check the brief itself:** a factual error, a hidden assumption, a contradiction with the files, or a prescribed fix that does not serve the stated goal. Name it with the brief's own wording (in a review turn, as a `findings` entry; in an implementation turn, at the top of the Assumptions list). If it blocks the work, stop as the rules say.
- **Scope and certainty:** for each claim in `report`, say whether you verified it (by which command) or assume it; when something is uncertain, name the cause (missing context, underspecified brief, or out of scope). Qualitative words only, no probabilities.
- When two readings remain equally plausible and the choice matters, do not pick silently: ask in `needs_user` (or `decisions_requested`), with the smallest fact that would decide it.
