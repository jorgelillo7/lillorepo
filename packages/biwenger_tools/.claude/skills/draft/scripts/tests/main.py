"""Pytest entrypoint for the draft skill's tests.

Unlike the other suites this one names its own directory: pytest skips any path
component starting with a dot, so a bare `pytest.main()` walks straight past
`.claude`, collects nothing and reports a green "no tests ran".
"""

import os
import sys

import pytest

if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    sys.exit(pytest.main([here, *sys.argv[1:]]))
