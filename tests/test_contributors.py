"""Tests for the contributor-list generation script."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "make_contributors.py"
)


def _load_script() -> Any:
    """Import the contributor script, which lives outside the package.

    Returns:
        Any: The imported module.
    """
    spec = importlib.util.spec_from_file_location("make_contributors", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_contributors = _load_script()


class _FakeResponse:
    """Minimal stand-in for a requests response."""

    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        """Do nothing: the fake response is always successful."""

    def json(self) -> Any:
        """Return the payload the response was built with.

        Returns:
            Any: The canned payload.
        """
        return self.payload


CONTRIBUTORS = [
    {
        "login": "octocat",
        "name": "The Octocat",
        "html_url": "https://github.com/octocat",
        "avatar_url": "https://avatars.githubusercontent.com/u/1?v=4",
        "contributions": 12,
    },
    {
        "login": "hubot",
        "name": None,
        "html_url": "https://github.com/hubot",
        "avatar_url": "https://avatars.githubusercontent.com/u/2?v=4",
        "contributions": 3,
    },
]


class RenderFragmentTests(unittest.TestCase):
    def test_lists_names_logins_and_counts(self) -> None:
        fragment = make_contributors.render_fragment(
            CONTRIBUTORS, "2026-01-02T03:04:05+00:00"
        )
        self.assertIn("The Octocat", fragment)
        self.assertIn("[octocat](https://github.com/octocat)", fragment)
        self.assertIn("| 12 |", fragment)
        self.assertIn("| 3 |", fragment)

    def test_falls_back_to_login_without_a_name(self) -> None:
        fragment = make_contributors.render_fragment(
            CONTRIBUTORS, "2026-01-02T03:04:05+00:00"
        )
        self.assertIn("[hubot](https://github.com/hubot)", fragment)

    def test_escapes_pipes_in_names(self) -> None:
        contributor = dict(CONTRIBUTORS[0], name="A|B")
        fragment = make_contributors.render_fragment(
            [contributor], "2026-01-02T03:04:05+00:00"
        )
        self.assertIn("A\\|B", fragment)

    def test_records_the_source_and_date(self) -> None:
        fragment = make_contributors.render_fragment(
            CONTRIBUTORS, "2026-01-02T03:04:05+00:00"
        )
        self.assertIn("graphs/contributors", fragment)
        self.assertIn("2026-01-02", fragment)


class SnapshotTests(unittest.TestCase):
    def test_snapshot_holds_the_contributor_records(self) -> None:
        snapshot = make_contributors.build_snapshot(
            CONTRIBUTORS, "owner/name", "2026-01-02T03:04:05+00:00"
        )
        self.assertEqual(snapshot["repo"], "owner/name")
        self.assertEqual(snapshot["generated_at"], "2026-01-02T03:04:05+00:00")
        self.assertEqual(len(snapshot["contributors"]), 2)
        self.assertEqual(snapshot["contributors"][0]["login"], "octocat")
        self.assertEqual(snapshot["contributors"][1]["name"], None)


class FetchTests(unittest.TestCase):
    def test_anonymous_commits_are_skipped(self) -> None:
        payload = CONTRIBUTORS + [{"name": "Anon", "contributions": 2}]
        with mock.patch.object(
            make_contributors.requests,
            "get",
            return_value=_FakeResponse(payload),
        ):
            contributors = make_contributors.fetch_contributors()
        self.assertEqual([c["login"] for c in contributors], ["octocat", "hubot"])

    def test_unexpected_payload_raises(self) -> None:
        with (
            mock.patch.object(
                make_contributors.requests,
                "get",
                return_value=_FakeResponse({"message": "Not Found"}),
            ),
            self.assertRaises(make_contributors.ContributorsError),
        ):
            make_contributors.fetch_contributors()


class CommittedArtefactsTests(unittest.TestCase):
    def test_generated_files_exist(self) -> None:
        self.assertTrue(make_contributors.FRAGMENT_PATH.exists())
        self.assertTrue(make_contributors.SNAPSHOT_PATH.exists())

    def test_snapshot_is_valid_json_with_contributors(self) -> None:
        snapshot = json.loads(
            make_contributors.SNAPSHOT_PATH.read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(snapshot["contributors"]), 1)
        for contributor in snapshot["contributors"]:
            self.assertTrue(contributor["login"])
            self.assertTrue(contributor["url"].startswith("https://github.com/"))

    def test_fragment_is_included_by_the_page(self) -> None:
        page = (
            make_contributors.ROOT / "reference" / "contributors.qmd"
        ).read_text(encoding="utf-8")
        self.assertIn("{{< include _contributors-list.md >}}", page)


if __name__ == "__main__":
    unittest.main()
