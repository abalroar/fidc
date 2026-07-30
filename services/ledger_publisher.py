"""Publish curation decisions from the app straight into the repository.

A decision taken in the Streamlit panel lands in two CSV files.  Until those
files are committed and pushed they exist only in the clone where the app is
running, which means the next session — here, in Codex or on another machine —
starts from the previous state and silently loses the work.

This module closes that gap.  It stages **only** the ledger files, never the
whole tree, so unrelated work in progress is left untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


#: The only two files this module is ever allowed to stage.
LEDGER_FILES: tuple[str, ...] = (
    "data/industry_study/taxonomy_review_actions.csv",
    "data/industry_study/taxonomy_review_audit.csv",
)

#: Used only when the clone has no identity configured, so that a decision is
#: never lost to a git configuration error.
FALLBACK_AUTHOR_NAME = "toma.conta fidcs"
FALLBACK_AUTHOR_EMAIL = "curadoria@toma.conta"

_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class RepositoryStatus:
    """What the panel needs to know before offering to publish."""

    is_repository: bool
    branch: str
    pending_files: tuple[str, ...]
    detail: str = ""

    @property
    def has_pending(self) -> bool:
        return bool(self.pending_files)


@dataclass(frozen=True)
class PublishResult:
    committed: bool
    pushed: bool
    detail: str


def _run(
    arguments: list[str], root: Path, *, check: bool = False
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=check,
    )


def _identity_arguments(root: Path) -> list[str]:
    name = _run(["config", "user.name"], root).stdout.strip()
    email = _run(["config", "user.email"], root).stdout.strip()
    if name and email:
        return []
    return [
        "-c",
        f"user.name={FALLBACK_AUTHOR_NAME}",
        "-c",
        f"user.email={FALLBACK_AUTHOR_EMAIL}",
    ]


def repository_status(
    root: Path, files: tuple[str, ...] = LEDGER_FILES
) -> RepositoryStatus:
    """Report the branch and which ledger files differ from the last commit."""

    try:
        inside = _run(["rev-parse", "--is-inside-work-tree"], root)
    except (OSError, subprocess.SubprocessError) as error:
        return RepositoryStatus(False, "", (), f"git indisponível: {error}")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return RepositoryStatus(False, "", (), "diretório não é um repositório git")

    branch = _run(["rev-parse", "--abbrev-ref", "HEAD"], root).stdout.strip()
    status = _run(["status", "--porcelain", "--", *files], root)
    if status.returncode != 0:
        return RepositoryStatus(True, branch, (), status.stderr.strip())
    pending = tuple(
        line[3:].strip()
        for line in status.stdout.splitlines()
        if line.strip()
    )
    return RepositoryStatus(True, branch, pending)


def publish_decisions(
    root: Path,
    *,
    message: str,
    files: tuple[str, ...] = LEDGER_FILES,
    push: bool = True,
) -> PublishResult:
    """Commit the ledger files and, optionally, push them to the remote.

    A rejected push is retried once after rebasing on the remote branch, which
    is what happens when the same ledger was advanced from another machine.
    """

    status = repository_status(root, files)
    if not status.is_repository:
        return PublishResult(False, False, status.detail)
    if not status.has_pending:
        return PublishResult(False, False, "Nenhuma decisão nova para publicar.")

    staged = _run(["add", "--", *files], root)
    if staged.returncode != 0:
        return PublishResult(False, False, staged.stderr.strip())

    committed = _run(
        [*_identity_arguments(root), "commit", "-m", message, "--", *files], root
    )
    if committed.returncode != 0:
        return PublishResult(False, False, committed.stderr.strip() or committed.stdout.strip())
    if not push:
        return PublishResult(True, False, "Commit criado; publicação remota não solicitada.")

    branch = status.branch or "HEAD"
    pushed = _run(["push", "origin", branch], root)
    if pushed.returncode == 0:
        return PublishResult(True, True, f"Publicado em origin/{branch}.")

    rebased = _run(["pull", "--rebase", "--autostash", "origin", branch], root)
    if rebased.returncode != 0:
        return PublishResult(
            True,
            False,
            "Commit criado localmente, mas o push falhou e o rebase também: "
            + (rebased.stderr.strip() or pushed.stderr.strip()),
        )
    retried = _run(["push", "origin", branch], root)
    if retried.returncode == 0:
        return PublishResult(
            True, True, f"Publicado em origin/{branch} após rebase no remoto."
        )
    return PublishResult(
        True,
        False,
        "Commit criado localmente, mas o push foi recusado: "
        + (retried.stderr.strip() or pushed.stderr.strip()),
    )
