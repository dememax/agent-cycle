#!/usr/bin/env python3.14
# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Byte-exact Markdown and reStructuredText section reader — agent-cycle project
"""Print one named section from a Markdown or reStructuredText document.

Usage: read-section.py FILE HEADING
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Heading:
    """One parsed heading and the first source line belonging to it."""

    text: str
    level: int
    start: int


def display(value: object) -> str:
    """Escape control characters so every diagnostic remains one line."""
    return str(value).replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


def markdown_headings(lines: list[str]) -> list[Heading]:
    """Return ATX headings outside backtick and tilde fenced blocks."""
    headings = []
    fence: tuple[str, int] | None = None
    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        if fence is not None:
            character, minimum = fence
            if re.fullmatch(rf" {{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*", content):
                fence = None
            continue

        opening = re.fullmatch(r" {0,3}(`{3,}|~{3,}).*", content)
        if opening is not None:
            marker = opening.group(1)
            fence = marker[0], len(marker)
            continue

        match = re.fullmatch(r" {0,3}(#{1,6}) (.*)", content)
        if match is not None:
            headings.append(Heading(match.group(2), len(match.group(1)), index))
    return headings


def adornment(line: str, title_length: int) -> str | None:
    """Return a valid repeated RST adornment character."""
    content = line.rstrip("\r\n")
    if len(content) < title_length or not content:
        return None
    character = content[0]
    if character.isalnum() or character.isspace() or content != character * len(content):
        return None
    return character


def rst_headings(lines: list[str]) -> list[Heading]:
    """Return RST headings, assigning levels by first-seen adornment style."""
    candidates: list[tuple[str, tuple[bool, str], int]] = []
    index = 0
    while index < len(lines):
        if index + 2 < len(lines):
            title = lines[index + 1].rstrip("\r\n").strip()
            overline = adornment(lines[index], len(title)) if title else None
            underline = adornment(lines[index + 2], len(title)) if title else None
            if overline is not None and underline == overline:
                candidates.append((title, (True, overline), index))
                index += 3
                continue

        title = lines[index].rstrip("\r\n").strip()
        underline = adornment(lines[index + 1], len(title)) if title and index + 1 < len(lines) else None
        if underline is not None:
            candidates.append((title, (False, underline), index))
            index += 2
            continue
        index += 1

    levels: dict[tuple[bool, str], int] = {}
    headings = []
    for title, style, start in candidates:
        level = levels.setdefault(style, len(levels) + 1)
        headings.append(Heading(title, level, start))
    return headings


def heading_matches(text: str, query: str) -> bool:
    """Match an exact title or a bounded numeric section prefix."""
    if text == query:
        return True
    number = query[1:] if query.startswith("§") else query
    if re.fullmatch(r"\d+(?:\.\d+)*", number) is None:
        return False
    return re.match(rf"{re.escape(number)}(?: |\. )", text) is not None


def fail(message: str) -> int:
    """Print one refusal diagnostic and return the usage-error status."""
    print(f"read-section: {message}", file=sys.stderr)
    return 2


def main(arguments: list[str]) -> int:
    """Read, parse and emit the one unambiguous requested section."""
    if len(arguments) != 2:
        return fail("usage: read-section.py FILE HEADING")

    filename, query = arguments
    path = Path(filename)
    if path.suffix not in {".md", ".rst"}:
        return fail(f"{display(path)}: unsupported file extension: {display(path.suffix)}")
    try:
        raw = path.read_bytes()
    except OSError:
        return fail(f"{display(path)}: cannot read")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return fail(f"{display(path)}: invalid UTF-8")

    lines = text.splitlines(keepends=True)
    headings = markdown_headings(lines) if path.suffix == ".md" else rst_headings(lines)
    matches = [heading for heading in headings if heading_matches(heading.text, query)]
    if not matches:
        return fail(f"heading not found: {display(query)}")
    if len(matches) > 1:
        numbers = ", ".join(str(heading.start + 1) for heading in matches)
        return fail(f"heading is ambiguous at lines {numbers}: {display(query)}")

    selected = matches[0]
    end = len(lines)
    for heading in headings:
        if heading.start > selected.start and heading.level <= selected.level:
            end = heading.start
            break
    sys.stdout.buffer.write("".join(lines[selected.start : end]).encode("utf-8"))
    print(f"{display(path)}:{selected.start + 1}-{end}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
