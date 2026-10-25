#!/bin/bash
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Entry point for codex-queue-turn.py — agent-cycle project
# Thin entry point; the implementation and its checks are in codex-queue-turn.py.
exec python3.14 -I "$(dirname "$(readlink -f "$0")")/codex-queue-turn.py" "$@"
