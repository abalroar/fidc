from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from services.ledger_publisher import (
    DEFAULT_BRANCH,
    LEDGER_FILES,
    _push_target,
    publish_decisions,
    redact,
    repository_status,
    resolve_push_credential,
)


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments], cwd=str(root), check=True, capture_output=True, text=True
    )


@pytest.fixture()
def repository(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    (root / "data" / "industry_study").mkdir(parents=True)
    _git(root, "init", "-q", "-b", "principal")
    for name in LEDGER_FILES:
        (root / name).write_text("review_id\n", encoding="utf-8")
    (root / "outro.txt").write_text("intocado\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=teste",
        "-c",
        "user.email=teste@local",
        "commit",
        "-qm",
        "estado inicial",
    )
    return root


def test_a_directory_without_git_is_reported_instead_of_raising(tmp_path: Path) -> None:
    status = repository_status(tmp_path)

    assert not status.is_repository
    assert status.detail
    assert not status.has_pending


def test_a_clean_repository_has_nothing_to_publish(repository: Path) -> None:
    status = repository_status(repository)

    assert status.is_repository
    assert status.branch == "principal"
    assert not status.has_pending

    result = publish_decisions(repository, message="nada", push=False)
    assert not result.committed
    assert "Nenhuma decisão nova" in result.detail


def test_a_changed_ledger_is_detected_and_committed(repository: Path) -> None:
    (repository / LEDGER_FILES[0]).write_text("review_id\n00000000000191\n", encoding="utf-8")

    status = repository_status(repository)
    assert status.has_pending

    result = publish_decisions(repository, message="uma decisão", push=False)
    assert result.committed
    assert not result.pushed

    assert not repository_status(repository).has_pending
    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=str(repository),
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.strip() == "uma decisão"


def test_publishing_never_stages_unrelated_work(repository: Path) -> None:
    """Work in progress on other files must survive a publication untouched."""

    (repository / LEDGER_FILES[0]).write_text("review_id\n00000000000191\n", encoding="utf-8")
    (repository / "outro.txt").write_text("trabalho em andamento\n", encoding="utf-8")

    publish_decisions(repository, message="somente o ledger", push=False)

    pending = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(repository),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "outro.txt" in pending
    assert "taxonomy_review_actions.csv" not in pending


def test_a_clone_without_identity_still_commits(repository: Path) -> None:
    _git(repository, "config", "--local", "user.name", "")
    _git(repository, "config", "--local", "user.email", "")
    (repository / LEDGER_FILES[1]).write_text("event_id\nabc\n", encoding="utf-8")

    result = publish_decisions(repository, message="sem identidade", push=False)

    assert result.committed


def test_a_missing_remote_reports_instead_of_losing_the_commit(repository: Path) -> None:
    (repository / LEDGER_FILES[0]).write_text("review_id\n00000000000191\n", encoding="utf-8")

    result = publish_decisions(repository, message="sem remoto", push=True)

    assert result.committed
    assert not result.pushed
    assert result.detail


def test_without_a_token_the_clone_credential_is_used(repository: Path) -> None:
    credential = resolve_push_credential(repository, {})

    assert not credential.configured
    assert credential.url == ""


def test_a_token_becomes_an_authenticated_push_url(repository: Path) -> None:
    _git(repository, "remote", "add", "origin", "https://github.com/abalroar/fidc.git")

    credential = resolve_push_credential(repository, {"github_token": "ghp_exemplo"})

    assert credential.configured
    assert credential.url == (
        "https://x-access-token:ghp_exemplo@github.com/abalroar/fidc.git"
    )


def test_the_repository_can_come_from_the_secrets(tmp_path: Path) -> None:
    """A clone with no usable remote still publishes when the secret says where."""

    credential = resolve_push_credential(
        tmp_path,
        {"github_token": "ghp_exemplo", "github_repository": "abalroar/fidc"},
    )

    assert credential.configured
    assert credential.url.endswith("@github.com/abalroar/fidc.git")


def test_a_token_with_url_characters_survives_the_round_trip(repository: Path) -> None:
    _git(repository, "remote", "add", "origin", "git@github.com:abalroar/fidc.git")

    credential = resolve_push_credential(repository, {"github_token": "a/b?c#d@e"})

    assert credential.url == (
        "https://x-access-token:a%2Fb%3Fc%23d%40e@github.com/abalroar/fidc.git"
    )


def test_a_token_without_a_repository_reports_instead_of_pushing_blind() -> None:
    credential = resolve_push_credential(Path("/nonexistent"), {"github_token": "x"})

    assert not credential.configured
    assert "github_repo" in credential.detail


def test_the_token_is_never_echoed_back_to_the_screen() -> None:
    """Git prints the remote URL on failure; the token must not ride along."""

    leaked = (
        "fatal: unable to access "
        "'https://x-access-token:ghp_segredo@github.com/abalroar/fidc.git/': 403"
    )

    assert "ghp_segredo" not in redact(leaked)
    assert "***@github.com" in redact(leaked)


def test_a_failed_authenticated_push_reports_without_the_token(repository: Path) -> None:
    (repository / LEDGER_FILES[0]).write_text("review_id\n00000000000191\n", encoding="utf-8")

    result = publish_decisions(
        repository,
        message="com token",
        push=True,
        secrets={"github_token": "ghp_segredo", "github_repository": "abalroar/fidc"},
    )

    assert result.committed
    assert not result.pushed
    assert "ghp_segredo" not in result.detail


def test_the_repo_key_of_the_portfolio_store_is_reused(tmp_path: Path) -> None:
    """One secrets entry serves both features; do not ask for the repo twice."""

    credential = resolve_push_credential(
        tmp_path,
        {
            "github_token": "ghp_exemplo",
            "github_repo": "abalroar/fidc",
            "github_portfolios_path": "portfolios.json",
        },
    )

    assert credential.configured
    assert credential.url.endswith("@github.com/abalroar/fidc.git")


def test_a_checked_out_branch_is_pushed_by_name() -> None:
    assert _push_target("principal", {}) == ("principal", "principal")


def test_a_detached_head_falls_back_to_the_configured_branch() -> None:
    """A deploy that checks out a commit has no branch to push back to."""

    assert _push_target("HEAD", {"github_branch": "producao"}) == (
        "producao",
        "HEAD:refs/heads/producao",
    )
    assert _push_target("", {}) == (DEFAULT_BRANCH, f"HEAD:refs/heads/{DEFAULT_BRANCH}")


def test_a_detached_head_still_publishes(repository: Path) -> None:
    _git(repository, "checkout", "-q", "--detach", "HEAD")
    (repository / LEDGER_FILES[0]).write_text("review_id\n00000000000191\n", encoding="utf-8")

    result = publish_decisions(repository, message="destacado", push=False)

    assert result.committed
