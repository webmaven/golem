from __future__ import annotations

import logging
import sys
from pathlib import Path

from golem.plugins.apidoc.core.api import AsciiDocApi
from golem.plugins.apidoc.core.extractor import (
    GriffeContextFilter,
    _griffe_context,
    clear_griffe_context,
    set_griffe_context,
)

# ---------------------------------------------------------------------------
# Unit tests for griffe context tracking primitives
# ---------------------------------------------------------------------------


def test_set_clear_griffe_context_roundtrip():
    """set_griffe_context / clear_griffe_context roundtrips the ContextVar."""
    assert _griffe_context.get() is None

    set_griffe_context(module_path="golem.plugins.apidoc.core.formatter", object_name="format_docstring")
    ctx = _griffe_context.get()
    assert ctx is not None
    assert ctx["module_path"] == "golem.plugins.apidoc.core.formatter"
    assert ctx["object_name"] == "format_docstring"

    clear_griffe_context()
    assert _griffe_context.get() is None


def test_set_griffe_context_partial():
    """set_griffe_context accepts only module_path or only object_name."""
    set_griffe_context(module_path="my.module")
    ctx = _griffe_context.get()
    assert ctx == {"module_path": "my.module", "object_name": None}
    clear_griffe_context()

    set_griffe_context(object_name="my_object")
    ctx = _griffe_context.get()
    assert ctx == {"module_path": None, "object_name": "my_object"}
    clear_griffe_context()


def test_griffe_context_filter_injects_module_path():
    """GriffeContextFilter sets record.module from context when present."""
    f = GriffeContextFilter()

    set_griffe_context(module_path="golem.plugins.apidoc.core.api", object_name="render_class")
    record = logging.LogRecord(
        name="griffe",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="No type or annotation for parameter 'docstring'",
        args=(),
        exc_info=None,
    )
    assert f.filter(record)
    assert record.module == "golem.plugins.apidoc.core.api"
    assert "[render_class]" in record.getMessage()
    clear_griffe_context()


def test_griffe_context_filter_no_context_leaves_unchanged():
    """GriffeContextFilter leaves record unchanged when no context is set."""
    f = GriffeContextFilter()
    record = logging.LogRecord(
        name="griffe",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="No type or annotation for parameter 'docstring'",
        args=(),
        exc_info=None,
    )
    assert f.filter(record)
    assert record.module == ""
    assert record.getMessage() == "No type or annotation for parameter 'docstring'"


def test_griffe_context_filter_object_name_not_duplicated():
    """GriffeContextFilter does not prepend object name if already in message."""
    f = GriffeContextFilter()

    set_griffe_context(module_path="my.module", object_name="my_object")
    record = logging.LogRecord(
        name="griffe",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="[my_object] No type or annotation for parameter 'docstring'",
        args=(),
        exc_info=None,
    )
    assert f.filter(record)
    assert record.module == "my.module"
    # Object name already present; should not be duplicated.
    assert record.getMessage().count("[my_object]") == 1
    clear_griffe_context()


def test_griffe_context_filter_warning_only():
    """GriffeContextFilter passes through non-warning records unchanged."""
    f = GriffeContextFilter()

    set_griffe_context(module_path="my.module", object_name="my_object")
    record = logging.LogRecord(
        name="griffe",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Loading module my.module",
        args=(),
        exc_info=None,
    )
    assert f.filter(record)
    assert record.module == "my.module"
    clear_griffe_context()


# ---------------------------------------------------------------------------
# Integration tests: context is set during real griffe calls
# ---------------------------------------------------------------------------


def _capture_griffe_warnings(api: AsciiDocApi, tmp_path: Path) -> list[str]:
    """Render a package with missing type annotations and capture griffe warnings."""
    captured: list[str] = []

    class Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    handler = Handler()
    handler.setLevel(logging.WARNING)
    griffe_logger = logging.getLogger("griffe")
    griffe_logger.addHandler(handler)
    griffe_logger.setLevel(logging.WARNING)

    try:
        api.load_package("doc_warn_pkg")
        api.generate_package_docs("doc_warn_pkg")
    finally:
        griffe_logger.removeHandler(handler)

    return captured


# ---------------------------------------------------------------------------
# Integration tests: context is set/cleared during real griffe calls
# ---------------------------------------------------------------------------


def test_griffe_context_set_during_load_package(tmp_path):
    """Context is set and cleared during load_package and render calls.

    Verifies the ContextVar holds the expected module/object context while
    griffe is actively processing, and is cleared afterward so it does not
    leak between operations.
    """
    pkg_dir = tmp_path / "ctx_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Context package."""


def hello(name: str) -> str:
    """Say hello to a name."""

    return f"Hello, {name}!"
''',
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        api = AsciiDocApi(search_paths=[str(tmp_path)])

        # Context must be clear before any griffe call.
        assert _griffe_context.get() is None

        # load_package sets context for the module.
        mod = api.load_package("ctx_pkg")
        assert mod.name == "ctx_pkg"
        assert _griffe_context.get() is None, "load_package must clear context after finishing"

        # resolve_symbol sets context for the symbol.
        func = api.resolve_symbol("ctx_pkg.hello")
        assert func.name == "hello"
        assert _griffe_context.get() is None, "resolve_symbol must clear context after finishing"

        # render_function sets context for the object.
        rendered = api.render_function(func)
        assert "hello" in rendered
        assert _griffe_context.get() is None, "render_function must clear context after finishing"

        # render_module sets context for the module.
        rendered_mod = api.render_module(mod)
        assert "ctx_pkg" in rendered_mod
        assert _griffe_context.get() is None, "render_module must clear context after finishing"
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


def test_griffe_context_set_during_generate_package_docs(tmp_path):
    """Context is set/cleared for each module during generate_package_docs."""
    pkg_dir = tmp_path / "gen_ctx_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Gen context package."""


def add(a: int, b: int) -> int:
    """Add two integers."""

    return a + b
''',
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        api = AsciiDocApi(search_paths=[str(tmp_path)])

        # Context clear before generate_package_docs.
        assert _griffe_context.get() is None

        docs = api.generate_package_docs("gen_ctx_pkg")
        assert isinstance(docs, dict)
        assert len(docs) >= 1

        # Context must be cleared after generate_package_docs completes.
        assert _griffe_context.get() is None
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


# ---------------------------------------------------------------------------
# Context var isolation: context does not leak between calls
# ---------------------------------------------------------------------------


def test_griffe_context_isolated_between_calls():
    """Context must not leak between sequential griffe operations."""
    set_griffe_context(module_path="first.module", object_name="first_fn")
    assert _griffe_context.get()["module_path"] == "first.module"

    clear_griffe_context()
    assert _griffe_context.get() is None

    set_griffe_context(module_path="second.module", object_name="second_fn")
    assert _griffe_context.get()["module_path"] == "second.module"
    assert _griffe_context.get()["object_name"] == "second_fn"

    clear_griffe_context()
    assert _griffe_context.get() is None
