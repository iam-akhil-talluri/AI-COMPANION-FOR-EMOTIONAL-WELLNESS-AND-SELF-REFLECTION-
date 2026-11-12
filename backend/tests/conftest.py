import os
from pathlib import Path

import pytest

# Lets the offline tests import the app without a real key (e.g. in CI).
# Skipped when .env exists, because an env var would override the real key there.
if not (Path(__file__).parent.parent / ".env").exists():
    os.environ.setdefault("OPENAI_API_KEY", "test-key")


def pytest_configure(config):
    config.addinivalue_line("markers", "live: calls the real OpenAI API (set RUN_LIVE_TESTS=1)")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_LIVE_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_LIVE_TESTS=1 to call the real Claude API")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
