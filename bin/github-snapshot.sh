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
snapshot_output=$(mktemp "${TMPDIR:-/tmp}/agent-cycle-snapshot.XXXXXX") || {
  echo "github-snapshot: cannot create temporary file" >&2
  exit 2
}
trap 'rm -f "${snapshot_output}"' 0 1 2 3 15
snapshot_status=0

fail_snapshot() {
  echo "github-snapshot: $1: $2 failed" >&2
  snapshot_status=2
}

for d in "${HOME}"/github/*/ "${HOME}"/github/*/*/; do
  [ -d "${d}.git" ] || [ -f "${d}.git" ] || continue
  r=${d%/}

  if git -C "${r}" rev-parse --verify -q 'HEAD^{commit}' >"${snapshot_output}" 2>/dev/null; then
    head=$(cat "${snapshot_output}")
  elif git -C "${r}" symbolic-ref -q HEAD >"${snapshot_output}" 2>/dev/null; then
    head_ref=$(cat "${snapshot_output}")
    case ${head_ref} in
      refs/heads/*) ;;
      *)
        fail_snapshot "${r}" HEAD
        continue
        ;;
    esac
    if ! git -C "${r}" check-ref-format "${head_ref}" >/dev/null 2>&1; then
      fail_snapshot "${r}" HEAD
      continue
    fi
    if ! git -C "${r}" for-each-ref --format='%(refname)' "${head_ref}" >"${snapshot_output}" 2>/dev/null; then
      fail_snapshot "${r}" HEAD
      continue
    fi
    if [ -s "${snapshot_output}" ]; then
      fail_snapshot "${r}" HEAD
      continue
    fi
    head=none
  else
    fail_snapshot "${r}" HEAD
    continue
  fi

  if ! git -C "${r}" for-each-ref --format='%(refname) %(objectname)' >"${snapshot_output}" 2>/dev/null; then
    fail_snapshot "${r}" refs
    continue
  fi
  refs=$(grep -v '^refs/codex/' "${snapshot_output}" | sha256sum | cut -c1-16)

  if ! git -C "${r}" for-each-ref refs/codex >"${snapshot_output}" 2>/dev/null; then
    fail_snapshot "${r}" refs/codex
    continue
  fi
  codex=$(wc -l <"${snapshot_output}")

  if ! git --no-optional-locks -C "${r}" status --porcelain=v1 -uall >"${snapshot_output}" 2>/dev/null; then
    fail_snapshot "${r}" status
    continue
  fi
  st=$(sha256sum <"${snapshot_output}" | cut -c1-16)
  echo "${r} head=${head} refs=${refs} codex_refs=${codex} status=${st}"
done

exit "${snapshot_status}"
