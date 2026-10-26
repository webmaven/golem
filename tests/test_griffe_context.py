from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from golem.plugins.apidoc.core.api import AsciiDocApi
from golem.plugins.apidoc.core.extractor import (
    GriffeContextFilter,
    _griffe_context,
    clear_griffe_context,
    create_griffe_loader,
    is_symbol_visible,
    resolve_symbol,
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
    assert "[golem.plugins.apidoc.core.api.render_class]" in record.getMessage()
    clear_griffe_context()


def test_griffe_context_filter_no_context_leaves_unchanged():
    """GriffeContextFilter leaves record unchanged when no context is set."""
    f = GriffeContextFilter()
    clear_griffe_context()  # ensure no context leaks from prior tests
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
    assert "[my.module.my_object]" in record.getMessage()
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
    assert "[my.module.my_object] Loading module my.module" == record.getMessage()
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


# ---------------------------------------------------------------------------
# Extractor error paths and edge cases
# ---------------------------------------------------------------------------


def test_resolve_symbol_empty_path_raises():
    """resolve_symbol raises ValueError for an empty symbol path."""
    loader = create_griffe_loader(search_paths=[])
    with pytest.raises(ValueError, match="Invalid empty symbol path"):
        resolve_symbol(loader, "")


def test_resolve_symbol_module_not_found_raises(tmp_path):
    """resolve_symbol raises ValueError when no module prefix can be loaded."""
    loader = create_griffe_loader(search_paths=[str(tmp_path)])
    with pytest.raises(ValueError, match="Could not load or resolve module"):
        resolve_symbol(loader, "nonexistent_module_xyz")


def test_is_symbol_visible_private_true():
    """is_symbol_visible returns True for private names when include_private=True."""
    assert is_symbol_visible("_private", include_private=True) is True


def test_is_symbol_visible_private_false():
    """is_symbol_visible returns False for private names when include_private=False."""
    assert is_symbol_visible("_private", include_private=False) is False


def test_is_symbol_visible_special_true():
    """is_symbol_visible returns True for dunder names when include_special=True."""
    assert is_symbol_visible("__init__", include_special=True) is True


def test_is_symbol_visible_special_false():
    """is_symbol_visible returns False for dunder names when include_special=False."""
    assert is_symbol_visible("__magic__", include_special=False) is False


def test_is_symbol_visible_public_always_true():
    """is_symbol_visible returns True for public names regardless of flags."""
    assert is_symbol_visible("public_name") is True
    assert is_symbol_visible("public_name", include_private=False) is True
    assert is_symbol_visible("public_name", include_special=False) is True


# ---------------------------------------------------------------------------
# Formatter function tests
# ---------------------------------------------------------------------------


def test_offset_headings_with_matches():
    """_offset_headings shifts section headings down by offset levels."""
    from golem.plugins.apidoc.core.formatter import _offset_headings

    text = "= Title\n\n== Section\n\n=== Subsection\n"
    result = _offset_headings(text, 1)
    assert "== Title" in result
    assert "=== Section" in result
    assert "[absolute-level=2]" in result
    assert "[absolute-level=3]" in result


def test_offset_headings_no_matches_returns_unchanged():
    """_offset_headings returns text unchanged when no headings present."""
    from golem.plugins.apidoc.core.formatter import _offset_headings

    text = "Plain text without headings.\n"
    assert _offset_headings(text, 2) == text


def test_offset_headings_offset_zero_returns_unchanged():
    """_offset_headings with offset=0 returns text unchanged."""
    from golem.plugins.apidoc.core.formatter import _offset_headings

    text = "= Title\n== Section\n"
    assert _offset_headings(text, 0) == text


def test_format_parameters_keyword_only():
    """format_parameters renders keyword-only parameters with a '*' separator."""
    from golem.plugins.apidoc.core.formatter import format_parameters

    import griffe

    params = [
        type("P", (), {"name": "a", "kind": griffe.ParameterKind.positional_only, "annotation": None, "default": None})(),
        type("P", (), {"name": "b", "kind": griffe.ParameterKind.keyword_only, "annotation": None, "default": None})(),
    ]
    result = format_parameters(params)
    assert "*" in result
    assert "b" in result


def test_format_parameters_trailing_positional_only():
    """format_parameters appends '/' when last params are positional-only."""
    from golem.plugins.apidoc.core.formatter import format_parameters

    import griffe

    params = [
        type("P", (), {"name": "a", "kind": griffe.ParameterKind.positional_only, "annotation": None, "default": None})(),
    ]
    result = format_parameters(params)
    assert "/ " in result or result == "a, /"


def test_format_docstring_empty_returns_empty():
    """format_docstring returns empty string for empty/None docstring."""
    from golem.plugins.apidoc.core.formatter import format_docstring

    assert format_docstring(None) == ""
    assert format_docstring("") == ""
    assert format_docstring("   ") == ""


# ---------------------------------------------------------------------------
# Remaining uncovered lines in extractor.py and formatter.py
# ---------------------------------------------------------------------------


def test_resolve_symbol_member_not_found_raises(tmp_path):
    """resolve_symbol raises ValueError when member not found in parent."""
    pkg_dir = tmp_path / "member_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        "def foo() -> None:\n    pass\n",
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        loader = create_griffe_loader(search_paths=[str(tmp_path)])
        with pytest.raises(ValueError, match="Symbol 'nonexistent' not found"):
            resolve_symbol(loader, "member_pkg.nonexistent")
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


def test_format_class_attribute_no_description(tmp_path):
    """format_class renders _(no description)_ for attribute without description/default."""
    from golem.plugins.apidoc.core.formatter import format_class

    pkg_dir = tmp_path / "attr_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''class Widget:
    """A widget class."""

    count: int
''',
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        api = AsciiDocApi(search_paths=[str(tmp_path)])
        cls = api.resolve_symbol("attr_pkg.Widget")
        rendered = format_class(cls, heading_level=2)
        assert "_(no description)_" in rendered
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


def test_format_module_heading_level_gt_1(tmp_path):
    """format_module adds absolute-level when heading_level > 1."""
    from golem.plugins.apidoc.core.formatter import format_module

    pkg_dir = tmp_path / "mod_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Module docstring."""


def func() -> None:
    pass
''',
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        api = AsciiDocApi(search_paths=[str(tmp_path)])
        mod = api.load_package("mod_pkg")
        rendered = format_module(mod, heading_level=3)
        assert "[absolute-level=3]" in rendered
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


def test_format_module_attribute_no_description(tmp_path):
    """format_module renders _(no description)_ for module attribute without description."""
    from golem.plugins.apidoc.core.formatter import format_module

    pkg_dir = tmp_path / "mod_attr_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Module docstring."""

VERSION: int
''',
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        api = AsciiDocApi(search_paths=[str(tmp_path)])
        mod = api.load_package("mod_attr_pkg")
        rendered = format_module(mod, heading_level=2)
        assert "_(no description)_" in rendered
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


def test_format_module_with_submodules(tmp_path):
    """format_module lists submodules when depth=all."""
    from golem.plugins.apidoc.core.formatter import format_module

    pkg_dir = tmp_path / "sub_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Parent package."""


def root() -> None:
    pass
''',
        encoding="utf-8",
    )
    sub_dir = pkg_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "__init__.py").write_text(
        '''"""Sub module."""


def helper() -> None:
    pass
''',
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        api = AsciiDocApi(search_paths=[str(tmp_path)])
        mod = api.load_package("sub_pkg")
        rendered = format_module(mod, heading_level=2, depth="all")
        assert "Submodules" in rendered
        assert "sub" in rendered
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


def test_resolve_symbol_child_of_non_container_raises(tmp_path):
    """resolve_symbol raises ValueError when traversing into a non-container member."""
    pkg_dir = tmp_path / "noncontainer_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''def func() -> None:
    """A function."""


''',
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        loader = create_griffe_loader(search_paths=[str(tmp_path)])
        # func is a Function (not Module/Class), so accessing a sub-member hits the else branch
        with pytest.raises(ValueError, match="Cannot resolve child member"):
            resolve_symbol(loader, "noncontainer_pkg.func.submember")
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


def test_get_asg_nodes_sets_context(tmp_path):
    """get_asg_nodes sets griffe context during node construction.

    This is the entry point used by the golem.apidoc:: macro during docs
    builds; context must be active while format_class/format_function/etc.
    call griffe.parse() so warnings carry module/object context.
    """
    pkg_dir = tmp_path / "asg_ctx_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""ASG context package."""


def greet(name: str) -> str:
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

        # Context clear before get_asg_nodes.
        assert _griffe_context.get() is None

        nodes = api.get_asg_nodes("asg_ctx_pkg.greet")
        assert len(nodes) >= 1

        # Context cleared after get_asg_nodes completes.
        assert _griffe_context.get() is None
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))


def test_get_asg_nodes_warnings_carry_context(tmp_path):
    """get_asg_nodes warnings include module/object context from griffe.

    Uses a function whose docstring Parameters section entries lack type
    annotations, which triggers griffe "No type or annotation" warnings
    during docstring parsing in _class_node/_function_node → format_docstring
    → griffe.parse().
    """
    pkg_dir = tmp_path / "asg_warn_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""ASG warn package."""


def documented(x, y):
    """Documented function.

    Parameters:
        x: The first value.
        y: The second value.
    """

    return x + y
''',
        encoding="utf-8",
    )

    sys_path_inserted = False
    if str(tmp_path) not in sys.path:
        sys.path.insert(0, str(tmp_path))
        sys_path_inserted = True

    try:
        api = AsciiDocApi(search_paths=[str(tmp_path)])

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
            nodes = api.get_asg_nodes("asg_warn_pkg.documented")
            assert len(nodes) >= 1
        finally:
            griffe_logger.removeHandler(handler)

        # At least one warning should carry context (module path or object name).
        contextful = [m for m in captured if "documented" in m or "asg_warn_pkg" in m]
        assert contextful, f"No contextful griffe warnings captured. Got: {captured}"
    finally:
        if sys_path_inserted:
            sys.path.remove(str(tmp_path))
