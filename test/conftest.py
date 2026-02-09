from pathlib import Path

import pytest

from config.feature_flags import FEATURE_FLAGS, set_flag


def _is_tnp_suite_test(node: pytest.Item) -> bool:
    """Enable TNP debug logging only for dedicated TNP test modules."""
    try:
        return Path(str(node.fspath)).name.startswith("test_tnp_")
    except Exception:
        return "test_tnp_" in str(getattr(node, "nodeid", ""))


@pytest.fixture(autouse=True)
def _tnp_debug_logging_only_for_tnp_suite(request: pytest.FixtureRequest):
    if not _is_tnp_suite_test(request.node):
        yield
        return

    previous = bool(FEATURE_FLAGS.get("tnp_debug_logging", False))
    set_flag("tnp_debug_logging", True)
    try:
        yield
    finally:
        set_flag("tnp_debug_logging", previous)
