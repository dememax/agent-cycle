# Copyright (C) 2026 Maxime P. DEMENTYEV
# SPDX-License-Identifier: GPL-3.0-only
# Black-box tests for the public-content push gate — agent-cycle project

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from .conftest import ROOT, IsolatedEnvironment

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

CHECK_PUBLIC = ROOT / "tools" / "check-public.sh"
ZERO_SHA = "0" * 40


def invented_value() -> str:
    """Return a generated deny-list value that is absent from tracked sources."""
    return bytes((86, 101, 108, 118, 101, 116, 79, 114, 98, 105, 116)).decode()


def generated_email(local: str) -> str:
    """Construct an example address without putting an address in this file."""
    return "@".join((local, ".".join(("example", "test"))))


@dataclass
class Repository:
    """A generated repository and its completely isolated Git environment."""

    path: Path
    deny_list: Path
    environment: dict[str, str]
    configured_email: str

    def git(
        self,
        arguments: Sequence[str],
        *,
        extra_env: Mapping[str, str] | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run local-only Git in the generated repository."""
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.path,
            env=self.environment | dict(extra_env or {}),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if check:
            assert result.returncode == 0, result.stderr
        return result

    def write_deny_list(self, *entries: str) -> None:
        """Write only generated rules to the isolated deny-list."""
        self.deny_list.write_text("\n".join(entries) + "\n", encoding="utf-8")

    def commit(
        self,
        path: str,
        content: str,
        *,
        message: str = "generated commit",
        author_email: str | None = None,
    ) -> str:
        """Commit one generated file and return the commit object name."""
        destination = self.path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        self.git(["add", "--", path])
        identity = {}
        if author_email is not None:
            identity = {
                "GIT_AUTHOR_NAME": "Generated Foreign Author",
                "GIT_AUTHOR_EMAIL": author_email,
            }
        self.git(["commit", "-q", "-m", message], extra_env=identity)
        return self.git(["rev-parse", "HEAD"]).stdout.strip()

    def remove_and_commit(self, path: str) -> str:
        """Remove one generated file in a new commit."""
        self.git(["rm", "-q", "--", path])
        self.git(["commit", "-q", "-m", "generated removal"])
        return self.git(["rev-parse", "HEAD"]).stdout.strip()

    def gate(
        self,
        *arguments: str,
        input_text: str | None = None,
        deny_list: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run the gate with its deny-list redirected into the fake home."""
        environment = self.environment | {
            "AGENT_CYCLE_DENY_LIST": str(deny_list or self.deny_list),
        }
        return subprocess.run(
            [CHECK_PUBLIC, *arguments],
            cwd=self.path,
            env=environment,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )


@pytest.fixture
def repository(tmp_path: Path, isolated_env: IsolatedEnvironment) -> Repository:
    """Create a repository whose system and global Git configuration are isolated."""
    path = tmp_path / "public-project"
    path.mkdir()
    global_config = isolated_env.home / "empty-gitconfig"
    global_config.touch()
    environment = isolated_env.variables | {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(global_config),
    }
    configured_email = generated_email("generated.author")
    repo = Repository(path, isolated_env.home / "generated-deny-list", environment, configured_email)
    repo.git(["init", "-q"])
    repo.git(["config", "user.name", "Generated Author"])
    repo.git(["config", "user.email", configured_email])
    repo.commit("initial.txt", "generated initial content\n", message="generated initial commit")
    repo.write_deny_list(f"fixed-i:{invented_value()}")
    return repo


def combined_output(result: subprocess.CompletedProcess[str]) -> str:
    """Combine both output channels for disclosure assertions."""
    return result.stdout + result.stderr


def test_clean_single_revision_returns_zero(repository: Repository) -> None:
    """A single revision means all reachable objects and succeeds when clean."""
    result = repository.gate("HEAD")

    assert result.returncode == 0, combined_output(result)
    assert combined_output(result) == ""


def test_blob_added_then_removed_is_still_scanned(repository: Repository) -> None:
    """Objects introduced and removed inside a range remain in its publication set."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    added = repository.commit("transient.txt", invented_value() + "\n")
    repository.remove_and_commit("transient.txt")

    result = repository.gate(f"{base}..HEAD")

    assert result.returncode == 1
    assert f"commit={added}" in result.stdout
    assert "kind=blob" in result.stdout
    assert "path=transient.txt" in result.stdout
    assert "line=1" in result.stdout
    assert "rule=deny-list entry 1" in result.stdout


@pytest.mark.parametrize("location", ["message", "path"])
def test_deny_hit_outside_blob_content(repository: Repository, location: str) -> None:
    """Commit messages and path names are publication content too."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    value = invented_value()
    if location == "message":
        commit = repository.commit("safe.txt", "generated\n", message=value)
    else:
        commit = repository.commit(f"{value}/safe.txt", "generated\n")

    result = repository.gate(f"{base}..HEAD")

    assert result.returncode == 1
    assert f"commit={commit}" in result.stdout
    assert f"kind={location}" in result.stdout
    assert value not in combined_output(result)


def test_fixed_i_is_case_insensitive(repository: Repository) -> None:
    """A fixed-i rule finds a differently cased substring."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    repository.write_deny_list(f"fixed-i:{invented_value().upper()}")
    repository.commit("fixed.txt", invented_value().lower() + "\n")

    result = repository.gate(f"{base}..HEAD")

    assert result.returncode == 1
    assert "rule=deny-list entry 1" in result.stdout


def test_word_rule_has_case_sensitive_word_boundaries(repository: Repository) -> None:
    """A word rule accepts punctuation boundaries but not case or suffix changes."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    value = invented_value()
    repository.write_deny_list(f"word:{value}")
    repository.commit("nonmatches.txt", f"{value.lower()} {value}s\n")

    nonmatches = repository.gate(f"{base}..HEAD")

    assert nonmatches.returncode == 0, combined_output(nonmatches)

    before_match = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    repository.commit("match.txt", f"~/{value}\n")

    match = repository.gate(f"{before_match}..HEAD")

    assert match.returncode == 1
    assert "rule=deny-list entry 1" in match.stdout


def test_regex_rule_supports_inline_flags(repository: Repository) -> None:
    """A regex entry is compiled by Python and accepts inline flags."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    stem = "".join(("generated", "token"))
    expression = "".join(("(?i)", stem, "[0-9]{2}"))
    repository.write_deny_list(f"regex:{expression}")
    repository.commit("regex.txt", stem.upper() + "42\n")

    result = repository.gate(f"{base}..HEAD")

    assert result.returncode == 1
    assert "rule=deny-list entry 1" in result.stdout


def test_home_path_distinguishes_literal_names_from_placeholders(repository: Repository) -> None:
    """Literal Unix and macOS homes are rejected; shorthands and placeholders are not."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    repository.commit("safe-homes.txt", "~/x\n/home/<user>/x\n/Users/<name>/x\n")

    safe = repository.gate(f"{base}..HEAD")

    assert safe.returncode == 0, combined_output(safe)

    before_literal = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    literal = "/".join(("", "home", "generated-person", "x"))
    repository.commit("literal-home.txt", literal + "\n")

    rejected = repository.gate(f"{before_literal}..HEAD")

    assert rejected.returncode == 1
    assert "rule=home path" in rejected.stdout


def test_email_rule_allows_configured_and_coauthor_addresses(repository: Repository) -> None:
    """The configured identity and named co-author trailers are the only email exceptions."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    codex = "<noreply@openai.com>"
    claude = "<noreply@anthropic.com>"
    message = f"Configured <{repository.configured_email}>\n\nCo-Authored-By: Codex GPT-5 {codex}\nCo-Authored-By: Claude Opus 5.5 {claude}"
    repository.commit("allowed-emails.txt", "generated\n", message=message)

    allowed = repository.gate(f"{base}..HEAD")

    assert allowed.returncode == 0, combined_output(allowed)

    before_foreign = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    foreign = generated_email("foreign.author")
    commit = repository.commit("foreign.txt", "generated\n", author_email=foreign)

    rejected = repository.gate(f"{before_foreign}..HEAD")

    assert rejected.returncode == 1
    assert f"commit={commit}" in rejected.stdout
    assert "kind=identity" in rejected.stdout
    assert "rule=email" in rejected.stdout
    assert foreign not in combined_output(rejected)


@pytest.mark.parametrize(
    "key",
    [
        "".join(("creator", "_user_id")),
        "".join(("creator", "_account_id")),
        "".join(("account", "_id")),
        "".join(("account", "Uuid")),
        "".join(("organization", "Uuid")),
        "".join(("user", "ID")),
        "".join(("user", "_id")),
    ],
)
def test_account_key_with_same_line_value_is_rejected(repository: Repository, key: str) -> None:
    """Every documented account-identifier spelling is rejected when it has a value."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    repository.commit("account.txt", f'"{key}": "generated-value"\n')

    result = repository.gate(f"{base}..HEAD")

    assert result.returncode == 1
    assert "rule=account key" in result.stdout


def test_content_reachable_only_before_range_is_not_scanned(repository: Repository) -> None:
    """A publication range excludes content already present at its lower boundary."""
    value = invented_value()
    already_pushed = repository.commit("old-private.txt", value + "\n")
    repository.remove_and_commit("old-private.txt")

    result = repository.gate(f"{already_pushed}..HEAD")

    assert result.returncode == 0, combined_output(result)


@pytest.mark.parametrize(
    ("contents", "mode"),
    [
        ("", None),
        ("# generated comment\n\n", None),
        ("unknown:generated\n", None),
        ("fixed-i:\n", None),
        ("regex:(generated\n", None),
        ("fixed-i:generated\n", 0),
    ],
)
def test_invalid_deny_lists_fail_closed(repository: Repository, contents: str, mode: int | None) -> None:
    """Empty, malformed, invalid and unreadable deny-lists are configuration errors."""
    repository.deny_list.write_text(contents, encoding="utf-8")
    if mode is not None:
        repository.deny_list.chmod(mode)

    result = repository.gate("HEAD")

    assert result.returncode == 2
    assert invented_value() not in combined_output(result)


def test_missing_deny_list_fails_closed(repository: Repository) -> None:
    """The gate never runs without an explicit or default deny-list."""
    missing = repository.deny_list.with_name("missing-deny-list")

    result = repository.gate("HEAD", deny_list=missing)

    assert result.returncode == 2


def test_unresolvable_range_fails_closed(repository: Repository) -> None:
    """A revision expression Git cannot resolve is an operational failure."""
    result = repository.gate("generated-missing-revision")

    assert result.returncode == 2


def test_failing_git_command_fails_closed(repository: Repository) -> None:
    """Object corruption cannot turn a scan into a successful result."""
    blob = repository.git(["rev-parse", "HEAD:initial.txt"]).stdout.strip()
    object_path = repository.path / ".git" / "objects" / blob[:2] / blob[2:]
    object_path.unlink()

    result = repository.gate("HEAD")

    assert result.returncode == 2


@pytest.mark.parametrize(
    "line",
    [
        "generated malformed input\n",
        "refs/heads/main not-a-sha refs/heads/main " + ZERO_SHA + "\n",
        "refs/heads/main " + ZERO_SHA[:-1] + " refs/heads/main " + ZERO_SHA + "\n",
    ],
)
def test_malformed_pre_push_input_fails_closed(repository: Repository, line: str) -> None:
    """The hook protocol is parsed strictly before any scan."""
    result = repository.gate("--pre-push", "generated-remote", input_text=line)

    assert result.returncode == 2


def test_pre_push_update_scans_remote_to_local(repository: Repository) -> None:
    """An updated ref scans commits reachable after its remote object."""
    remote = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    local = repository.commit("update.txt", invented_value() + "\n")
    line = f"refs/heads/main {local} refs/heads/main {remote}\n"

    result = repository.gate("--pre-push", "generated-remote", input_text=line)

    assert result.returncode == 1


def test_pre_push_new_ref_excludes_remote_tracking_history(repository: Repository) -> None:
    """A new ref scans local history that no tracking ref for that remote contains."""
    remote = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    repository.git(["update-ref", "refs/remotes/generated-remote/main", remote])
    local = repository.commit("new-ref.txt", invented_value() + "\n")
    line = f"refs/heads/topic {local} refs/heads/topic {ZERO_SHA}\n"

    result = repository.gate("--pre-push", "generated-remote", input_text=line)

    assert result.returncode == 1


def test_pre_push_deletion_scans_nothing(repository: Repository) -> None:
    """Deleting a remote ref publishes no object content."""
    remote = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    line = f"(delete) {ZERO_SHA} refs/heads/old {remote}\n"

    result = repository.gate("--pre-push", "generated-remote", input_text=line)

    assert result.returncode == 0, combined_output(result)


@pytest.mark.parametrize("foreign_tagger", [False, True])
def test_pre_push_annotated_tag_scans_message_and_tagger_identity(
    repository: Repository,
    foreign_tagger: bool,
) -> None:
    """An annotated tag publishes both its message and tagger identity."""
    head = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    repository.git(["update-ref", "refs/remotes/generated-remote/main", head])
    tag_name = "generated-tag-foreign" if foreign_tagger else "generated-tag-message"
    extra_env = {}
    message = "generated tag"
    expected_rule = "deny-list entry 1"
    if foreign_tagger:
        extra_env = {
            "GIT_COMMITTER_NAME": "Generated Foreign Tagger",
            "GIT_COMMITTER_EMAIL": generated_email("foreign.tagger"),
        }
        expected_rule = "email"
    else:
        message = invented_value()
    repository.git(["tag", "-a", tag_name, "-m", message], extra_env=extra_env)
    tag_object = repository.git(["rev-parse", tag_name]).stdout.strip()
    line = f"refs/tags/{tag_name} {tag_object} refs/tags/{tag_name} {ZERO_SHA}\n"

    result = repository.gate("--pre-push", "generated-remote", input_text=line)

    assert result.returncode == 1
    assert "kind=tag" in result.stdout
    assert f"rule={expected_rule}" in result.stdout


def test_finding_output_never_discloses_match_or_deny_value(repository: Repository) -> None:
    """Diagnostics identify the location and rule without echoing protected material."""
    base = repository.git(["rev-parse", "HEAD"]).stdout.strip()
    value = invented_value()
    repository.commit("disclosure.txt", f"prefix {value} suffix\n")

    result = repository.gate(f"{base}..HEAD")
    output = combined_output(result)

    assert result.returncode == 1
    assert "kind=blob" in output
    assert "path=disclosure.txt" in output
    assert "line=1" in output
    assert "rule=deny-list entry 1" in output
    assert value not in output
