# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Cold-reader documentation drift tests — agent-cycle project

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "cold-reader-manifest.toml"
GLOSSARY = ROOT / "docs" / "glossary.rst"
GLOSSARY_FILE_SUFFIXES = (".json", ".md", ".py", ".rst", ".sh", ".toml")
TEMPLATE_NAMES = (
    "implementation-brief.md",
    "review-brief.md",
    "orientation-brief.md",
    "exact-exception-brief.md",
)
TEMPLATE_SCHEMAS = {
    "implementation-brief.md": "implementation-result-v1.json",
    "review-brief.md": "review-result-v1.json",
    "orientation-brief.md": "review-result-v1.json",
    "exact-exception-brief.md": "implementation-result-v1.json",
}
SCENARIO_STEPS = {
    "roles-and-boundaries",
    "bootstrap",
    "drive-a-turn",
    "audit-and-review",
    "handle-an-incident",
    "renew-sessions",
    "release",
}
COMMON_TEMPLATE_MARKERS = (
    "[S0 DRIVER: <driver>]",
    "**1. Status.**",
    "**2. Context.**",
    "**3. Work item.**",
    "**4. Rules.**",
    "**5. Final message.**",
    "<project>",
    "<repository>",
    "<pinned-tools>/schemas/",
)


def _python_environment_variables() -> set[str]:
    variables: set[str] = set()
    for path in (ROOT / "bin").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and (
                    isinstance(node.value.value, ast.Name)
                    and node.value.value.id == "os"
                    and node.value.attr == "environ"
                    and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)
                )
            ):
                variables.add(node.slice.value)
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (
                isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "os"
                and node.func.value.attr == "environ"
                and node.func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                variables.add(node.args[0].value)
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(
                isinstance(target, ast.Name) and target.id == "RETIRED_PROFILE_VARIABLES" for target in node.targets
            ):
                continue
            if isinstance(node.value, ast.Tuple):
                variables.update(
                    element.value
                    for element in node.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                )
    return variables


def _shell_environment_variables() -> set[str]:
    variables: set[str] = set()
    pattern = re.compile(r"\$\{([A-Z][A-Z0-9_]*)")
    for path in (ROOT / "bin").glob("*.sh"):
        variables.update(pattern.findall(path.read_text(encoding="utf-8")))
    return variables


def _glossary_terms(text: str) -> set[str]:
    return set(re.findall(r"^ {3}(?![: ])(\S(?:.*\S)?)$", text, flags=re.MULTILINE))


def test_cold_reader_contract_has_not_drifted() -> None:
    failures: list[str] = []
    manifest: dict[str, object] = {}
    if not MANIFEST.is_file():
        failures.append("cold-reader-manifest.toml is missing")
    else:
        with MANIFEST.open("rb") as stream:
            manifest = tomllib.load(stream)

    scenario = manifest.get("scenario", [])
    if not isinstance(scenario, list):
        failures.append("manifest scenario must be an array of tables")
        scenario = []
    actual_steps = {entry.get("step") for entry in scenario if isinstance(entry, dict)}
    if actual_steps != SCENARIO_STEPS:
        failures.append(f"manifest scenario steps differ: {sorted(actual_steps, key=str)}")

    referenced_paths: set[str] = set()
    for entry in scenario:
        if not isinstance(entry, dict) or not isinstance(entry.get("authorities"), list):
            failures.append("each manifest scenario needs an authorities array")
            continue
        referenced_paths.update(path for path in entry["authorities"] if isinstance(path, str))
    for relative in sorted(referenced_paths):
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or str(pure) != relative:
            failures.append(f"manifest path is not canonical and relative: {relative}")
        elif not (ROOT / relative).exists():
            failures.append(f"manifest path does not exist: {relative}")

    a2i_path = ROOT / "templates" / "a2i-block.md"
    a2i = a2i_path.read_bytes() if a2i_path.is_file() else b""
    if not a2i:
        failures.append("templates/a2i-block.md is missing or empty")
    for name in TEMPLATE_NAMES:
        path = ROOT / "templates" / name
        if not path.is_file():
            failures.append(f"templates/{name} is missing")
            continue
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in COMMON_TEMPLATE_MARKERS if marker not in text]
        if "<base>" not in text:
            missing.append("<base>")
        if "<work-item>" not in text:
            missing.append("<work-item>")
        if TEMPLATE_SCHEMAS[name] not in text:
            missing.append(TEMPLATE_SCHEMAS[name])
        if missing:
            failures.append(f"templates/{name} lacks markers: {', '.join(missing)}")
        if a2i and not path.read_bytes().endswith(a2i):
            failures.append(f"templates/{name} does not end with the byte-identical A2I block")

    public_paths = list((ROOT / "docs").glob("*.rst"))
    public_paths.extend((ROOT / "templates").glob("*.md") if (ROOT / "templates").is_dir() else ())
    if MANIFEST.is_file():
        public_paths.append(MANIFEST)
    private_path = re.compile(r"/(?:home|Users)/[^/\s]+/")
    for path in public_paths:
        if private_path.search(path.read_text(encoding="utf-8")):
            failures.append(f"private absolute path in {path.relative_to(ROOT)}")

    operational = _python_environment_variables() | _shell_environment_variables()
    documented = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "docs").glob("*.rst"))
    missing_variables = sorted(variable for variable in operational if variable not in documented)
    if missing_variables:
        failures.append(f"operational environment variables are undocumented: {', '.join(missing_variables)}")

    glossary_text = ""
    if not GLOSSARY.is_file():
        failures.append("docs/glossary.rst is missing")
    else:
        glossary_text = GLOSSARY.read_text(encoding="utf-8")
    index_text = (ROOT / "docs" / "index.rst").read_text(encoding="utf-8")
    if not re.search(r"^ {3}glossary$", index_text, flags=re.MULTILINE):
        failures.append("docs/index.rst does not include glossary in its toctree")

    decisions_text = (ROOT / "docs" / "decisions.rst").read_text(encoding="utf-8")
    operational_variables = _python_environment_variables() | _shell_environment_variables()
    for term in sorted(_glossary_terms(glossary_text)):
        if term.endswith(GLOSSARY_FILE_SUFFIXES) or term.endswith("/"):
            matches = [ROOT / term] if "/" in term else list(ROOT.rglob(term))
            if not any(path.exists() for path in matches):
                failures.append(f"glossary file or tool term does not exist: {term}")
        elif re.fullmatch(r"[A-Z][A-Z0-9_]*_[A-Z0-9_]+", term):
            if term not in operational_variables:
                failures.append(f"glossary environment-variable term does not exist: {term}")
        elif re.fullmatch(r"[A-Z][A-Z0-9-]*/[A-Za-z0-9-]+", term) and term not in decisions_text:
            failures.append(f"glossary decision term does not exist: {term}")

    assert not failures, "\n".join(failures)
