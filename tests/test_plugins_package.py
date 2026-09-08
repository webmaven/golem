import golem.plugins
from golem.plugins import (
    HOOK_NAMESPACE,
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
    assert hasattr(golem.plugins, "GolemBuildAbortError")
    assert hasattr(golem.plugins, "BuildResult")
    assert "GolemBuildAbortError" in golem.plugins.__all__
    assert "BuildResult" in golem.plugins.__all__


def test_golem_build_abort_error_is_importable():
    from golem.plugins import GolemBuildAbortError

    assert issubclass(GolemBuildAbortError, Exception)


def test_build_result_is_importable():
    from pathlib import Path
    from golem.plugins import BuildResult

    r = BuildResult(compiled_files=[Path("a.html")], output_dir=Path("dist"))
    assert r.compiled_files == [Path("a.html")]
    assert r.output_dir == Path("dist")


def test_on_build_start_hookspec_exists():
    from golem.plugins import GolemSpecs

    assert hasattr(GolemSpecs, "on_build_start")


def test_on_build_finish_hookspec_exists():
    from golem.plugins import GolemSpecs

    assert hasattr(GolemSpecs, "on_build_finish")


def test_on_build_start_registered_in_plugin_manager():
    from golem.plugins import get_plugin_manager

    pm = get_plugin_manager()
    assert hasattr(pm.hook, "on_build_start")


def test_on_build_finish_registered_in_plugin_manager():
    from golem.plugins import get_plugin_manager

    pm = get_plugin_manager()
    assert hasattr(pm.hook, "on_build_finish")
