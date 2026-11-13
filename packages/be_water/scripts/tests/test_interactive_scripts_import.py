"""The interactive tools drive a human through prompts, so their logic lives
in the web library and is tested there. What can rot here unseen is the
script itself: an import of something renamed fails only on the day it is
next run."""

import importlib

import pytest


@pytest.mark.parametrize("name", ["audit_data", "audit_photos", "revert_water"])
def test_the_script_imports_and_has_a_main(name):
    module = importlib.import_module(f"packages.be_water.scripts.{name}")
    assert callable(module.main)
