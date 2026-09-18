import golem.plugins
from golem.plugins import (
    HOOK_NAMESPACE,
    GolemPlugin,
    GolemSpecs,
    get_plugin_manager,
    hookimpl,
    hookspec,
)


def test_plugins_is_package():
    """Verify that golem.plugins is a package directory (has __path__)."""
    assert hasattr(golem.plugins, "__path__")


def test_plugins_exports():
    """Verify that golem.plugins exports all required symbols."""
    assert HOOK_NAMESPACE == "golem"
    assert hookspec is not None
    assert hookimpl is not None
    assert GolemSpecs is not None
    assert callable(get_plugin_manager)
    assert GolemPlugin is not None
