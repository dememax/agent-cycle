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
| `templates/` | Material sources for turn briefs and their permanent blocks |
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
do, with `//`. The other exceptions are `templates/a2i-block.md` and
`templates/compaction-block.md`: they are byte-identical to their source
blocks and carry no repository header.

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
| check_rst | 0.7.5 | release `0.7.5` in its public repository | `check_rst --version` |
| check_formatting | 0.5.5 | release `0.5.5` in its public repository | `check_formatting --version` |
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

After an RST edit, run check_rst's three-step loop, described in the next
section.

## Documentation structure

The documentation is reStructuredText in `docs/`, built with Sphinx and
structured like check_rst's. RST uses the system-installed `check_rst`
command, invoked by name. Universal syntax, options and semantic rules belong
to `check_rst --help`, `check_rst COMMAND --help` and check_rst's
[guide](https://github.com/dememax/check_rst/blob/main/docs/guide.rst); this
repository records only its local facts. The workflow below relies on
`outline`'s `o` and `u` style codes, so it needs check_rst 0.7.3 or later.

`.check_rst.toml` declares the Sphinx source `docs` and the build directory
`/tmp/agent-cycle-sphinx-build`. All of `docs/` is maintained: it is a clean
full baseline, which `check_formatting --all` scans recursively through
`[rst].dir`. No file there is generated or excluded.

After an RST edit, run from the repository root:

```bash
check_rst check --skip-fixable
check_rst fix --fast
check_rst check
```

The first command is the semantic review: it hides what `fix` would resolve,
so the WARNINGs and non-fixable ERRORs it shows are yours to review and
resolve before any mutation. The second is the mechanical mutation: it applies
only fixable corrections. The third is the final validation of the result.
Bare selection is Git-scoped; explicit files and `--recursive` mean whole-file
intent. In a shared dirty worktree, pass the same owned-file allowlist with
`--git-scope` to all three commands, for example
`check_rst check --skip-fixable --git-scope docs/turn.rst`.

For a new heading, write a nine-character check_rst title placeholder (a
check_rst convention, not RST syntax) in the style of its sibling titles, as
`outline` shows it on their lines: `o` means the same line above and below the
title, `u` an underline only. Every title in `docs/` has an overline, like
check_rst's. Leave a blank line before and after the heading. For a new depth,
use the next free section character that `outline` reports. Let `fix --fast`
compute the adornment geometry; never count adornment characters, not even in
a scratch file. Never use one character both with and without an overline in a
file: Docutils reads the two forms as two styles, and `fix` refuses that
ambiguity.

Global options such as `--sphinx-src` and `--no-config` go before the command:
`check_rst --no-config check FILE`.

For a cold reader, use `check_rst outline FILE` when the structure or target
is unknown, and `check_rst context ENTRY FILE` for one known entry or explicit
label. Use `check_rst targets --exact LABEL` when a label's file is unknown.
These queries report physical locations: read a reported range directly, since
a raw text match cannot establish depth, parentage or entry boundaries. Use
`check_rst refs FILE` for a document's links, `check_rst refs --target LABEL`
for a label's exact uses, and `check_rst compare` to explain an existing Git
change. Never truncate check_rst output or a diff preview with a pipe.

## Commits

Keep commits focused. The body explains the context, the findings, the
chosen solution, its safety boundary and the validation. Write the message
to a file and commit with `git commit -F <file>`. Each commit carries one
trailer naming the agent:

- Codex: `Co-Authored-By: Codex GPT-5 <noreply@openai.com>`
- Claude Code: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

Never override the clone's configured author identity.
