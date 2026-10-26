<!--
Copyright (C) 2026 Maxime P. DEMENTYEV
SPDX-License-Identifier: GPL-3.0-only
-->

# agent-cycle

Tools and procedures for a reviewer-implementer pair of AI agents. See
[README.md](README.md) for what they do. This file covers conventions for
working *on* this repository.

## Purpose and boundary

The repository holds the process and its tooling, never a project's work or
history. A project's plans, records and evidence stay with that project or
in its maintainers' private notes. Run state stays in
`~/.local/state/agent-cycle/<project>/`, outside the repository.

**This repository is public.** It must never contain:
- private data from any project the cycle serves: names of private
  repositories, corpora or clients, their content, or paths into them;
- account identifiers from agent logs, or excerpts of real logs;
  test logs are generated;
- absolute home-directory paths: write `~` or `Path.home()`;
- text copied from the maintainers' private notes. Documents here are
  written for this repository.

A push gate refuses protected patterns in the content and metadata a push
would publish. Its deny-list stays outside the repository; the gate runs before
any push.

## Repository layout

| Path | Purpose |
|---|---|
| `bin/` | The command-line tools |
| `tools/` | The public-content gate and its tracked pre-push hook |
| `tests/` | Generated-log tests and the isolated fake Codex CLI |
| `schemas/` | Versioned final-message contracts |
| `profiles/` | Tracked project profiles |
| `docs/` | Sphinx documentation in reStructuredText |
| `.check_formatting.toml` | What check_formatting checks, and where |
| `.check_rst.toml` | check_rst's Sphinx facts, for the verified documentation build |
| `pyproject.toml` | Ruff and mypy rules, shared with check_rst and check_formatting |
| `.shellcheckrc` | ShellCheck policy |
| `.prettierrc`, `package.json`, `package-lock.json` | Prettier, pinned, for JSON and JSONC |
| `.vscode/` | VS Code workspace defaults and recommended extensions |

## File header comment

Every nontrivial file starts with this block, in the comment syntax of its
format (`#` for Python, shell and TOML, after any shebang line; `<!-- -->`
for Markdown; `..` comments for RST):

```text
Copyright (C) 2026 Maxime P. DEMENTYEV
SPDX-License-Identifier: GPL-3.0-only
<one-line description of the file's purpose> — agent-cycle project
```

`GPL-3.0-only`, not "or later". The description line is omitted when the
file name already says it. `LICENSE` stays the verbatim GPL text. Plain
JSON has no comment syntax and carries no header; JSONC files (`.vscode/`)
do, with `//`.

## Development method

Use TDD for behavioral changes, one RED/GREEN pair per correction:

1. Add the smallest failing test that states the predicate or regression.
2. Confirm that it fails for the intended reason, and commit it (RED).
3. Implement the minimal coherent change, and commit it (GREEN). A GREEN
   that edits its RED's assertions says so in its message.

The tools fail closed. A change must keep every refusal path: a malformed
log line, an ambiguous candidate, a running turn, a pending submission or
a profile mismatch stops the tool with a message; it never guesses.

## Validation

Python commands use Python 3.14 explicitly, and so do the tools' shebang
lines: the formatting rules target Python 3.14 syntax. Ruff 0.16.9 and
ShellCheck are system executables; mypy is 2.2.0. Prettier is pinned in
`package.json`: run `npm install --ignore-scripts` once after cloning.

The project profile declares the full ordered validation, including every
check in `.check_formatting.toml`. Run it once through the validation runner:

```bash
AGENT_CYCLE_PROFILE="$PWD/profiles/agent-cycle.toml" \
  python3.14 bin/validate.py --base BASE
```

The runner retains every step's raw output and prints failures in full. The
pytest suite uses only generated logs and isolates every subprocess from the
real Codex home, CLI, repositories and state. `check_formatting --all` runs
Ruff (format and lint), mypy, check_rst on `docs/`, ShellCheck and Prettier.
check_rst reads `.check_rst.toml` and therefore also builds the documentation
with Sphinx: any Sphinx warning or error in a checked file fails the check. Fix
findings in the code or the documents; do not weaken a configuration to obtain
a clean run. A remaining suppression is the narrowest error-code-specific
form, with its reason.

**Current state:** Ruff, mypy, ShellCheck, Prettier and check_rst are clean;
`LINT-1` cleared the semantic findings inherited at import.

After an RST edit, run check_rst's loop on `docs/` (`check --skip-fixable`,
`fix --fast`, `check`) and review its semantic warnings.

## Documentation structure

The documentation is reStructuredText built with Sphinx, structured like
check_rst's. Titles have an overline, like check_rst's. Declare a new
title with a nine-character placeholder of the sibling titles' style, and
let `check_rst fix --fast` materialize the adornment lengths.

## Commits

Keep commits focused. The body explains the context, the findings, the
chosen solution, its safety boundary and the validation. Write the message
to a file and commit with `git commit -F <file>`. Each commit carries one
trailer naming the agent:

- Codex: `Co-Authored-By: Codex GPT-5 <noreply@openai.com>`
- Claude Code: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

Never override the clone's configured author identity.
