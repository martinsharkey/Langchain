"""
Tests for the hot-reload code watcher in app.py.

The critical property: when src/ or scripts/ code changes, the engine thread must
pick up the NEW code — not the stale module cached in sys.modules. This is what
_purge_app_modules() guarantees.
"""
import sys
import os
import importlib
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app


@pytest.fixture
def _restore_modules():
    """Snapshot sys.modules and restore it after the test so purging src.* does
    not break the session-scoped config.DATA_DIR isolation for later tests."""
    snapshot = dict(sys.modules)
    yield
    # restore any modules the test purged (re-import is not needed; just put back)
    for name in list(sys.modules.keys()):
        if name not in snapshot:
            del sys.modules[name]
    for name, mod in snapshot.items():
        sys.modules[name] = mod


def test_purge_app_modules_drops_src_and_scripts(_restore_modules):
    """_purge_app_modules must remove every cached src.* / scripts.* module so a
    fresh import re-reads the changed source."""
    import src.config  # noqa: F401
    import src.core_rules  # noqa: F401
    import src.learning.param_optimizer  # noqa: F401

    assert "src.config" in sys.modules
    assert "src.learning.param_optimizer" in sys.modules

    purged = app._purge_app_modules()

    assert "src.config" in purged
    assert "src.learning.param_optimizer" in purged
    assert "src.config" not in sys.modules
    assert "src.learning.param_optimizer" not in sys.modules
    # unrelated stdlib modules are untouched
    assert "os" in sys.modules
    assert "json" in sys.modules


def test_purge_app_modules_ignores_non_app_modules(_restore_modules):
    """Only src.* / scripts.* are purged; stdlib and third-party stay cached."""
    import json  # noqa: F401
    import pytest  # noqa: F401

    purged = app._purge_app_modules()

    assert "json" not in purged
    assert "pytest" not in purged
    assert "json" in sys.modules


def test_restart_engine_helpers_exist():
    """The hot-reload restart path must expose the purge + restart helpers."""
    assert callable(app._purge_app_modules)
    assert callable(app._restart_engine)
    assert callable(app._trigger_reload)
    assert callable(app.start_hot_reload)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
