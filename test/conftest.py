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
    debug_defaults = {
        "tnp_debug_logging": False,
        "extrude_debug": False,
        "sketch_debug": False,
        "sketch_input_logging": False,
        "viewport_debug": False,
    }

    if not _is_tnp_suite_test(request.node):
        # Harte Isolation: Non-TNP-Tests laufen immer mit deaktiviertem
        # Debug-Flags, auch wenn ein anderes Testmodul Flags global setzt.
        for key, value in debug_defaults.items():
            set_flag(key, value)
        yield
        for key, value in debug_defaults.items():
            set_flag(key, value)
        return

    previous = bool(FEATURE_FLAGS.get("tnp_debug_logging", False))
    set_flag("tnp_debug_logging", True)
    try:
        yield
    finally:
        set_flag("tnp_debug_logging", previous)
