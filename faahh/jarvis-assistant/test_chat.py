import sys

import pytest


if __name__ == "__main__":
    raise SystemExit(pytest.main(["-q", "tests/test_chat.py"]))
