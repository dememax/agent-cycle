#!/bin/sh
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Snapshot of every Git repository's refs and status — agent-cycle project
# Print one line per Git repository under ~/github: path, HEAD, a hash of all
# refs outside refs/codex/, the count of refs/codex/ refs, and a hash of the
# working-tree status. Read-only: --no-optional-locks keeps `git status` from
# refreshing the index. refs/codex/ holds the VS Code Codex extension's
# turn-diff checkpoints (one per panel turn); they are counted separately so
# that an expected checkpoint does not hide or fake a change to other refs.
for d in "${HOME}"/github/*/ "${HOME}"/github/*/*/; do
  [ -d "${d}.git" ] || [ -f "${d}.git" ] || continue
  r=${d%/}
  head=$(git -C "${r}" rev-parse --verify -q HEAD || echo none)
  refs=$(git -C "${r}" for-each-ref --format='%(refname) %(objectname)' | grep -v '^refs/codex/' | sha256sum | cut -c1-16)
  codex=$(git -C "${r}" for-each-ref refs/codex | wc -l)
  st=$(git --no-optional-locks -C "${r}" status --porcelain=v1 -uall 2>/dev/null | sha256sum | cut -c1-16)
  echo "${r} head=${head} refs=${refs} codex_refs=${codex} status=${st}"
done
