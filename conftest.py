"""Pytest configuration for non-interactive CI runs."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")


def pytest_collection_modifyitems(config, items):
    skip_interactive = pytest.mark.skip(reason="interactive TTY demo; not a CI regression test")
    for item in items:
        if item.fspath and item.fspath.basename in {
            "test_inquirer.py",
            "test_simple_interactive.py",
        }:
            item.add_marker(skip_interactive)
