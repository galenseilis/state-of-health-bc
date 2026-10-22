"""Generate the project's contributor list from GitHub's contributors API.

Reads the repository's contributors from GitHub and writes two artefacts:

* ``reference/_contributors-list.md`` — the Markdown fragment included by
  ``reference/contributors.qmd``;
* ``data/contributors.json`` — a JSON snapshot of the same data.

The fragment is committed so the documentation site renders without
network access; re-run the script to refresh it. A ``GITHUB_TOKEN``
environment variable is used when present, which raises the API rate
limit. Run with:

    uv run python scripts/make_contributors.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
REPO = "galenseilis/state-of-health-bc"
CONTRIBUTORS_URL = "https://api.github.com/repos/{repo}/contributors"
USER_URL = "https://api.github.com/users/{login}"
FRAGMENT_PATH = ROOT / "reference" / "_contributors-list.md"
SNAPSHOT_PATH = ROOT / "data" / "contributors.json"
AUTH_ENV_VAR = "GITHUB_TOKEN"
USER_AGENT = "sohbc/0.1 (+https://galenseilis.github.io/state-of-health-bc)"
TIMEOUT = 30
PER_PAGE = 100


class ContributorsError(RuntimeError):
    """Raised when the GitHub API returns something unusable."""


def _headers(token: str | None) -> dict[str, str]:
    """Build the request headers for the GitHub API.

    Args:
        token: Personal access token, or None for anonymous access.

    Returns:
        dict: Headers to send with each API request.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _now() -> str:
    """Return the current UTC time in ISO 8601 format (no microseconds).

    Returns:
        str: Current UTC timestamp.
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def fetch_contributors(
    repo: str = REPO, token: str | None = None
) -> list[dict[str, Any]]:
    """Fetch the contributors of a GitHub repository.

    Anonymous commits (no linked account) are skipped: they have no
    profile to link to, and their e-mail addresses are not published.

    Args:
        repo: Repository in ``owner/name`` form.
        token: Personal access token, or None for anonymous access.

    Returns:
        list[dict]: Contributor records, as returned by the GitHub API.

    Raises:
        ContributorsError: If the API returns an unexpected payload.
    """
    contributors: list[dict[str, Any]] = []
    page = 1
    while True:
        response = requests.get(
            CONTRIBUTORS_URL.format(repo=repo),
            params={"per_page": PER_PAGE, "page": page},
            headers=_headers(token),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ContributorsError(f"unexpected response for {repo}: {payload!r}")
        contributors.extend(payload)
        if len(payload) < PER_PAGE:
            break
        page += 1
    return [c for c in contributors if c.get("login") and c.get("html_url")]


def fetch_display_name(
    login: str, token: str | None = None
) -> str | None:
    """Fetch the display name of a GitHub user.

    Args:
        login: GitHub user name.
        token: Personal access token, or None for anonymous access.

    Returns:
        str | None: The user's display name, or None if unavailable.
    """
    try:
        response = requests.get(
            USER_URL.format(login=login),
            headers=_headers(token),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        name = response.json().get("name")
    except (requests.RequestException, ValueError, AttributeError):
        return None
    return name.strip() if isinstance(name, str) and name.strip() else None


def _cell(text: str) -> str:
    """Escape text so it survives a Markdown table cell.

    Args:
        text: Raw text to place in a cell.

    Returns:
        str: Text safe to embed in a Markdown table cell.
    """
    return text.replace("|", "\\|")


def render_fragment(
    contributors: list[dict[str, Any]], generated_at: str, repo: str = REPO
) -> str:
    """Render the contributor list as a Markdown table.

    Args:
        contributors: Contributor records from the GitHub API.
        generated_at: Timestamp of the snapshot the list was built from.
        repo: Repository in ``owner/name`` form.

    Returns:
        str: Markdown fragment for inclusion in a documentation page.
    """
    lines = [
        "| Contributor | Contributions |",
        "|:-----------|--------------:|",
    ]
    for contributor in contributors:
        login = _cell(contributor["login"])
        profile = contributor["html_url"]
        name = contributor.get("name") or login
        avatar = contributor.get("avatar_url")
        portrait = (
            f"[![{login}]({avatar}){{width=40}}]({profile}) "
            if avatar
            else ""
        )
        lines.append(
            f"| {portrait}{_cell(name)} ([{login}]({profile})) "
            f"| {contributor.get('contributions', 0)} |"
        )
    day = generated_at[:10]
    lines.append("")
    lines.append(
        f"Generated from the repository's "
        f"[GitHub contributors list](https://github.com/{repo}/graphs/contributors) "
        f"on {day}."
    )
    return "\n".join(lines) + "\n"


def build_snapshot(
    contributors: list[dict[str, Any]], repo: str, generated_at: str
) -> dict[str, Any]:
    """Build the JSON snapshot of the contributor list.

    Args:
        contributors: Contributor records from the GitHub API.
        repo: Repository in ``owner/name`` form.
        generated_at: Timestamp of the snapshot.

    Returns:
        dict: Snapshot payload.
    """
    return {
        "schema_version": 1,
        "repo": repo,
        "generated_at": generated_at,
        "contributors": [
            {
                "login": contributor["login"],
                "name": contributor.get("name"),
                "url": contributor["html_url"],
                "avatar_url": contributor.get("avatar_url"),
                "contributions": contributor.get("contributions", 0),
            }
            for contributor in contributors
        ],
    }


def main(argv: list[str] | None = None) -> int:
    """Fetch the contributor list and write the generated files.

    Args:
        argv: Command-line arguments.

    Returns:
        int: Zero on success, non-zero if the list could not be fetched
        and no previously generated list is available.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        default=REPO,
        help="GitHub repository in owner/name form (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    token = os.environ.get(AUTH_ENV_VAR) or None
    try:
        contributors = fetch_contributors(repo=args.repo, token=token)
        for contributor in contributors:
            contributor["name"] = fetch_display_name(
                contributor["login"], token=token
            )
    except (requests.RequestException, ContributorsError) as exc:
        print(f"warning: could not fetch contributors: {exc}", file=sys.stderr)
        if FRAGMENT_PATH.exists() and SNAPSHOT_PATH.exists():
            print("keeping the previously generated contributor list")
            return 0
        return 1

    contributors.sort(key=lambda c: (-c.get("contributions", 0), c["login"]))
    generated_at = _now()

    FRAGMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FRAGMENT_PATH.write_text(
        render_fragment(contributors, generated_at, repo=args.repo),
        encoding="utf-8",
    )
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(
        json.dumps(
            build_snapshot(contributors, args.repo, generated_at),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    for path in (FRAGMENT_PATH, SNAPSHOT_PATH):
        print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
