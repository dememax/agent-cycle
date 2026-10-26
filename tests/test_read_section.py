# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Generated-document tests for the section reader — agent-cycle project

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from .conftest import PYTHON, ROOT

if TYPE_CHECKING:
    from pathlib import Path

READER = ROOT / "bin" / "read-section.py"


def run_reader(path: Path, heading: str) -> subprocess.CompletedProcess[bytes]:
    """Run the section reader without interpreting its byte streams."""
    return subprocess.run(
        [PYTHON, READER, path, heading],
        capture_output=True,
        check=False,
    )


def test_markdown_nested_section_stops_at_same_level(tmp_path: Path) -> None:
    document = tmp_path / "plan.md"
    document.write_bytes(b"# Plan\n\n## Target\nparent\n### Child\nchild\n## Next\nnext\n")

    result = run_reader(document, "Target")

    assert result.returncode == 0, result.stderr
    assert result.stdout == b"## Target\nparent\n### Child\nchild\n"
    assert result.stderr == f"{document}:3-6\n".encode()


@pytest.mark.parametrize("fence", ["```", "~~~"], ids=["backtick", "tilde"])
def test_markdown_ignores_heading_inside_fence(tmp_path: Path, fence: str) -> None:
    document = tmp_path / "plan.md"
    text = f"# Plan\n## Target\nbefore\n{fence}python\n## Not a section\n{fence}\nafter\n## Next\n"
    document.write_text(text, encoding="utf-8")

    result = run_reader(document, "Target")

    assert result.returncode == 0, result.stderr
    expected = f"## Target\nbefore\n{fence}python\n## Not a section\n{fence}\nafter\n".encode()
    assert result.stdout == expected
    assert result.stderr == f"{document}:2-7\n".encode()


def test_markdown_number_match_does_not_match_longer_number(tmp_path: Path) -> None:
    document = tmp_path / "record.md"
    document.write_text(
        "# Record\n## 5.10 Later\nwrong\n## 5.1 Selected\nright\n## 6 End\n",
        encoding="utf-8",
    )

    result = run_reader(document, "5.1")

    assert result.returncode == 0, result.stderr
    assert result.stdout == b"## 5.1 Selected\nright\n"
    assert result.stderr == f"{document}:4-5\n".encode()


def test_markdown_section_sign_matches_trailing_period_form(tmp_path: Path) -> None:
    document = tmp_path / "record.md"
    document.write_text("# Record\n## 17. Renewal state\nbody\n## 18. Next\n", encoding="utf-8")

    result = run_reader(document, "§17")

    assert result.returncode == 0, result.stderr
    assert result.stdout == b"## 17. Renewal state\nbody\n"
    assert result.stderr == f"{document}:2-3\n".encode()


def test_markdown_whole_text_match(tmp_path: Path) -> None:
    document = tmp_path / "notes.md"
    document.write_text("# Notes\n## Exact heading text\nbody\n", encoding="utf-8")

    result = run_reader(document, "Exact heading text")

    assert result.returncode == 0, result.stderr
    assert result.stdout == b"## Exact heading text\nbody\n"
    assert result.stderr == f"{document}:2-3\n".encode()


def test_rst_adornment_order_defines_section_levels(tmp_path: Path) -> None:
    document = tmp_path / "record.rst"
    document.write_text(
        "########\n"
        "Record\n"
        "########\n"
        "\n"
        "Summary\n"
        "*******\n"
        "\n"
        "Target\n"
        "======\n"
        "body\n"
        "\n"
        "Child\n"
        "-----\n"
        "child\n"
        "\n"
        "Next\n"
        "====\n"
        "next\n",
        encoding="utf-8",
    )

    result = run_reader(document, "Target")

    assert result.returncode == 0, result.stderr
    assert result.stdout == b"Target\n======\nbody\n\nChild\n-----\nchild\n\n"
    assert result.stderr == f"{document}:8-15\n".encode()

    result = run_reader(document, "Record")
    assert result.returncode == 0, result.stderr
    assert result.stdout == document.read_bytes()
    assert result.stderr == f"{document}:1-18\n".encode()


def test_ambiguous_heading_fails_with_line_numbers(tmp_path: Path) -> None:
    document = tmp_path / "notes.md"
    document.write_text("## Repeated\nfirst\n\n## Repeated\nsecond\n", encoding="utf-8")

    result = run_reader(document, "Repeated")

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == b"read-section: heading is ambiguous at lines 1, 4: Repeated\n"


@pytest.mark.parametrize(
    ("kind", "suffix", "content", "heading", "message"),
    [
        ("missing", ".md", None, "Absent", "cannot read"),
        ("invalid-utf8", ".md", b"# \xff\n", "Invalid", "invalid UTF-8"),
        ("unknown-extension", ".txt", b"# Heading\n", "Heading", "unsupported file extension: .txt"),
    ],
    ids=["missing", "invalid-utf8", "unknown-extension"],
)
def test_input_errors_fail_closed(
    tmp_path: Path,
    kind: str,
    suffix: str,
    content: bytes | None,
    heading: str,
    message: str,
) -> None:
    document = tmp_path / f"{kind}{suffix}"
    if content is not None:
        document.write_bytes(content)

    result = run_reader(document, heading)

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == f"read-section: {document}: {message}\n".encode()


def test_missing_heading_fails_closed(tmp_path: Path) -> None:
    document = tmp_path / "notes.md"
    document.write_text("# Present\n", encoding="utf-8")

    result = run_reader(document, "Absent")

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == b"read-section: heading not found: Absent\n"


def test_unreadable_file_fails_closed(tmp_path: Path) -> None:
    document = tmp_path / "unreadable.md"
    document.write_text("# Hidden\n", encoding="utf-8")
    document.chmod(0)

    result = run_reader(document, "Hidden")

    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr == f"read-section: {document}: cannot read\n".encode()
