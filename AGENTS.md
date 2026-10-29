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
| `templates/` | Material sources for turn briefs and the A2I block |
| `docs/` | Sphinx documentation in reStructuredText |
| `cold-reader-manifest.toml` | Cold-reader scenario steps and their authorities |
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
do, with `//`. The one other exception is `templates/a2i-block.md`: it is
byte-identical to its source block and carries no repository header.

## Development environment

The command-line tools in `bin/` use only the Python standard library and
other modules from `bin/`; their runtime has no third-party Python dependency.
Development and validation use these versions:

| Component | Version | Installation source | Verification command |
|---|---:|---|---|
| Python | 3.14.10 | system distribution | `python3.14 --version` |
| Ruff | 0.17.3 | Python Package Index | `ruff --version` |
| mypy | 2.3.1 | Python Package Index | `mypy --version` |
| pytest | 9.1.1 | Python Package Index | `python3.14 -m pytest --version` |
| Sphinx | 9.1.0 | Python Package Index | `python3.14 -c 'import sphinx; print(sphinx.__version__)'` |
| ShellCheck | 0.11.0 | system distribution | `shellcheck --version` |
| check_rst | 0.7.4 | release `0.7.4` in its public repository | `check_rst --version` |
| check_formatting | 0.5.3 | release `0.5.3` in its public repository | `check_formatting --version` |
| Prettier | 3.9.10 | npm registry through `package-lock.json` | `./node_modules/.bin/prettier --version` |

Git and Node.js with npm are also required, but the project does not pin their
versions. Install the Node dependency with `npm install --ignore-scripts`.

A local `.venv/` is supported and ignored by Git. It may hold the Python
packages above; the system tools must remain available on `PATH`. The
repository has no requirements file, Python lock file or otherwise locked
Python environment, so contributors install the documented versions
explicitly. `package-lock.json` is the repository's only dependency lock file.

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
lines: the formatting rules target Python 3.14 syntax. The development
versions and their installation sources are listed above.

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

To build the Sphinx HTML documentation directly, independently of check_rst,
run:

```bash
python3.14 -m sphinx -W --keep-going -b html docs docs/_build/html
```

Run it in a fresh export when validating a commit so generated files cannot
hide a worktree dependency. In the worktree, `docs/_build/` is ignored.

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
