"""Offline release-metadata checks for the public harness package."""

from __future__ import annotations

from pathlib import Path
import tomllib
import unittest

from pvz_runtime.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]


class HarnessReleaseTests(unittest.TestCase):
    def test_public_package_metadata_and_entry_points_are_versioned(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as handle:
            project = tomllib.load(handle)["project"]
        self.assertEqual(project["name"], "pvz-ai-harness")
        self.assertEqual(project["version"], "0.2.0")
        self.assertEqual(project["license"]["text"], "GPL-3.0-only")
        self.assertEqual(project["scripts"]["pvz-runtime-test"], "pvz_runtime.cli:main")
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertTrue((ROOT / "THIRD_PARTY_NOTICES.md").is_file())

    def test_read_only_cli_defaults_to_manual_focus_policy(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.focus_mode, "manual")
        self.assertFalse(args.pretty)


if __name__ == "__main__":
    unittest.main()
