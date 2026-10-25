# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Sphinx build configuration for the documentation — agent-cycle project

from __future__ import annotations

import datetime

project = "agent-cycle"
author = "Maxime P. DEMENTYEV"
current_year = datetime.datetime.now(tz=datetime.UTC).year
copyright_years = "2026" if current_year == 2026 else f"2026-{current_year}"
copyright = f"{copyright_years}, {author}"
language = "en"

extensions = ["sphinx.ext.autosectionlabel"]
autosectionlabel_prefix_document = True
exclude_patterns = ["_build"]
source_suffix = {".rst": "restructuredtext"}
root_doc = "index"

html_theme = "alabaster"

rst_prolog = f"""\
.. |project| replace:: {project}
.. |author| replace:: {author}
.. |copyright| replace:: {copyright}
"""
