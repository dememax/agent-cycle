#!/bin/sh
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Stable shell entry point for commit-pinned gate installation — agent-cycle project

script_path=$(readlink -f "$0") || exit 2
script_dir=$(dirname "${script_path}") || exit 2
exec python3.14 -I "${script_dir}/install-gate.py" "$@"
