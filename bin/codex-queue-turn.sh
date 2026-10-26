#!/bin/bash
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Entry point for codex-queue-turn.py — agent-cycle project
# Thin entry point; the implementation and its checks are in codex-queue-turn.py.
script_path=$(readlink -f "$0")
script_dir=$(dirname "${script_path}")
exec python3.14 -I "${script_dir}/codex-queue-turn.py" "$@"
