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
import re
import subprocess
from typing import Any, Mapping
from urllib.parse import quote, urlsplit, urlunsplit


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

#: Keys accepted in ``st.secrets`` for the write credential, in order.
TOKEN_SECRET_KEYS: tuple[str, ...] = (
    "github_token",
    "GITHUB_TOKEN",
    "ledger_github_token",
)
#: Optional ``owner/repo`` override, for when the clone has no usable remote.
REPOSITORY_SECRET_KEYS: tuple[str, ...] = ("github_repository", "GITHUB_REPOSITORY")

#: GitHub accepts any username with a token; this is the documented one.
TOKEN_USERNAME = "x-access-token"

_TOKEN_IN_URL = re.compile(r"(https?://)[^/@\s]*@")


@dataclass(frozen=True)
class PushCredential:
    """Where the push should go and with which token, if any.

    ``url`` is never written into ``.git/config``: it is passed as an argument
    to a single ``git push``, so the token does not survive the command.
    """

    url: str = ""
    configured: bool = False
    detail: str = ""


def redact(text: str) -> str:
    """Strip any credential embedded in a URL before the text is shown.

    Git echoes the remote URL in several error messages.  Without this, a failed
    push would print the token to the screen of whoever is using the panel.
    """

    return _TOKEN_IN_URL.sub(r"\1***@", str(text))


def _first_secret(secrets: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        try:
            value = secrets[key]
        except Exception:  # noqa: BLE001 - Streamlit raises on missing keys.
            continue
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _remote_repository(root: Path) -> str:
    """Read ``owner/repo`` from the configured remote, ignoring any credential."""

    try:
        url = _run(["remote", "get-url", "origin"], root).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    if not url:
        return ""
    path = url.split("github.com", 1)[-1] if "github.com" in url else urlsplit(url).path
    slug = path.lstrip(":/").removesuffix(".git")
    parts = [part for part in slug.split("/") if part]
    return "/".join(parts[-2:]) if len(parts) >= 2 else ""


def resolve_push_credential(
    root: Path, secrets: Mapping[str, Any] | None = None
) -> PushCredential:
    """Build the authenticated push URL from the secret, when one is set.

    With no secret the result is empty and the caller pushes through whatever
    credential the clone already has — the behaviour on a personal machine.  On
    a locked-down host, where no credential helper is available, the secret is
    what makes the push possible at all.
    """

    secrets = secrets or {}
    token = _first_secret(secrets, TOKEN_SECRET_KEYS)
    if not token:
        return PushCredential(detail="Sem token nos secrets; usando a credencial do clone.")
    repository = _first_secret(secrets, REPOSITORY_SECRET_KEYS) or _remote_repository(root)
    if not repository:
        return PushCredential(
            detail=(
                "Token encontrado, mas não foi possível descobrir o repositório. "
                "Defina github_repository = \"owner/repo\" nos secrets."
            )
        )
    netloc = f"{TOKEN_USERNAME}:{quote(token, safe='')}@github.com"
    url = urlunsplit(("https", netloc, f"/{repository}.git", "", ""))
    return PushCredential(url=url, configured=True, detail=f"Publicando em {repository}.")


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
    secrets: Mapping[str, Any] | None = None,
) -> PublishResult:
    """Commit the ledger files and, optionally, push them to the remote.

    A rejected push is retried once after rebasing on the remote branch, which
    is what happens when the same ledger was advanced from another machine.

    When ``secrets`` carries a GitHub token the push goes to an authenticated
    HTTPS URL built on the spot.  Nothing about it is persisted, and every
    message returned from here is redacted, so the token cannot reach the
    screen through a git error.
    """

    status = repository_status(root, files)
    if not status.is_repository:
        return PublishResult(False, False, status.detail)
    if not status.has_pending:
        return PublishResult(False, False, "Nenhuma decisão nova para publicar.")

    staged = _run(["add", "--", *files], root)
    if staged.returncode != 0:
        return PublishResult(False, False, redact(staged.stderr.strip()))

    committed = _run(
        [*_identity_arguments(root), "commit", "-m", message, "--", *files], root
    )
    if committed.returncode != 0:
        return PublishResult(
            False, False, redact(committed.stderr.strip() or committed.stdout.strip())
        )
    if not push:
        return PublishResult(True, False, "Commit criado; publicação remota não solicitada.")

    branch = status.branch or "HEAD"
    credential = resolve_push_credential(root, secrets)
    remote = credential.url or "origin"

    pushed = _run(["push", remote, branch], root)
    if pushed.returncode == 0:
        return PublishResult(True, True, f"Publicado em origin/{branch}.")

    rebased = _run(["pull", "--rebase", "--autostash", remote, branch], root)
    if rebased.returncode != 0:
        return PublishResult(
            True,
            False,
            redact(
                "Commit criado localmente, mas o push falhou e o rebase também: "
                + (rebased.stderr.strip() or pushed.stderr.strip())
            ),
        )
    retried = _run(["push", remote, branch], root)
    if retried.returncode == 0:
        return PublishResult(
            True, True, f"Publicado em origin/{branch} após rebase no remoto."
        )
    return PublishResult(
        True,
        False,
        redact(
            "Commit criado localmente, mas o push foi recusado: "
            + (retried.stderr.strip() or pushed.stderr.strip())
        ),
    )
