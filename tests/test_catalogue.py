"""Tests for the data-source catalogue and CLI."""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from sohbc import __version__, catalogue
from sohbc.__main__ import main
from sohbc.catalogue import (
    CATALOGUE_PATH,
    DOWNLOAD_KINDS,
    FORMS,
    ORIGINS,
    ROOT_ENV_VAR,
    TEMPORAL,
    CatalogueError,
    _discover_root,
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


class RootDiscoveryTests(unittest.TestCase):
    repo_root = Path(__file__).resolve().parents[1]

    def test_finds_checkout_from_a_subdirectory(self) -> None:
        original = Path.cwd()
        try:
            os.chdir(self.repo_root / "data")
            root = _discover_root()
        finally:
            os.chdir(original)
        self.assertEqual(root, self.repo_root)

    def test_env_var_overrides_discovery(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {ROOT_ENV_VAR: tmp}),
        ):
            self.assertEqual(_discover_root(), Path(tmp).resolve())

    def test_env_var_catalogue_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "data" / "catalogue"
            target.mkdir(parents=True)
            shutil.copy(CATALOGUE_PATH, target / "sources.yml")
            with mock.patch.dict(os.environ, {ROOT_ENV_VAR: tmp}):
                sources = load()
        self.assertGreaterEqual(len(sources), 1)

    def test_missing_checkout_error_explains(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "elsewhere" / "sohbc" / "catalogue.py"
            with (
                mock.patch.dict(os.environ, {ROOT_ENV_VAR: ""}),
                mock.patch.object(catalogue, "__file__", str(outside)),
            ):
                original = Path.cwd()
                try:
                    os.chdir(tmp)
                    with self.assertRaises(CatalogueError) as ctx:
                        load()
                finally:
                    os.chdir(original)
        self.assertIn("no project checkout found", str(ctx.exception))

    def test_invalid_env_root_error_explains(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {ROOT_ENV_VAR: tmp}),
            self.assertRaises(CatalogueError) as ctx,
        ):
            load()
        self.assertIn(ROOT_ENV_VAR, str(ctx.exception))


class CliTests(unittest.TestCase):
    def test_validate_returns_zero(self) -> None:
        self.assertEqual(main(["validate"]), 0)

    def test_version_flag(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer), self.assertRaises(SystemExit) as ctx:
            main(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn(f"sohbc {__version__}", buffer.getvalue())


class PackageTests(unittest.TestCase):
    def test_public_api_is_importable(self) -> None:
        import sohbc

        for name in sohbc.__all__:
            getattr(sohbc, name)
        self.assertTrue(sohbc.__version__)

    def test_library_load_matches_cli(self) -> None:
        import sohbc

        self.assertEqual(len(sohbc.load()), len(load()))


if __name__ == "__main__":
    unittest.main()
