"""Tests for the data-source catalogue and CLI."""

from __future__ import annotations

import unittest

from sohbc.__main__ import main
from sohbc.catalogue import (
    DOWNLOAD_KINDS,
    FORMS,
    ORIGINS,
    TEMPORAL,
    load,
)


class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = load()

    def test_catalogue_is_not_empty(self) -> None:
        self.assertGreaterEqual(len(self.sources), 1)

    def test_keys_unique(self) -> None:
        keys = [s.key for s in self.sources]
        self.assertEqual(len(keys), len(set(keys)))

    def test_enums_are_valid(self) -> None:
        for s in self.sources:
            self.assertIn(s.form, FORMS, s.key)
            self.assertIn(s.origin, ORIGINS, s.key)
            self.assertIn(s.temporal_behaviour, TEMPORAL, s.key)

    def test_urls_are_http(self) -> None:
        for s in self.sources:
            self.assertTrue(s.url.startswith(("http://", "https://")), s.key)

    def test_automated_downloads_are_configured(self) -> None:
        for s in self.sources:
            self.assertIn(s.download["kind"], DOWNLOAD_KINDS, s.key)
            if s.automated:
                self.assertTrue(s.download.get("url"), s.key)

    def test_manual_sources_have_access_notes(self) -> None:
        for s in self.sources:
            if not s.automated:
                self.assertTrue(s.form_of_access, s.key)


class CliTests(unittest.TestCase):
    def test_validate_returns_zero(self) -> None:
        self.assertEqual(main(["validate"]), 0)


if __name__ == "__main__":
    unittest.main()
