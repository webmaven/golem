from __future__ import annotations

import click
from click.testing import CliRunner

from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins import get_plugin_manager


def test_apidoc_plugin_registration():
    from golem.plugins import apidoc

    pm = get_plugin_manager()
    pm.register(apidoc)
    assert pm.is_registered(apidoc)


def test_on_pre_parse_macro_replacement(tmp_path):
    from golem.plugins import apidoc

    # Create a target package to document
    pkg_dir = tmp_path / "calc_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Calculator module."""
def multiply(x: int, y: int) -> int:
    """Multiply two numbers.

    Args:
        x: First factor.
        y: Second factor.

    Returns:
        Product of x and y.
    """
    return x * y
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Arithmetic Guide

Here is our multiply function:

golem:apidoc[target="calc_pkg.multiply"]

And more content.
"""
        # Initialize plugin or call on_pre_parse directly
        res = apidoc.on_pre_parse(raw_content=raw_doc)
        assert "golem:apidoc" not in res
        assert "def multiply(x: int, y: int) -> int:" in res
        assert "Multiply two numbers." in res
        assert "Arithmetic Guide" in res
    finally:
        sys.path.remove(str(tmp_path))


def test_on_pre_parse_syntax_variants(tmp_path):
    from golem.plugins import apidoc

    pkg_dir = tmp_path / "syn_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Syntax test pkg."""
def test_fn() -> None:
    """A test function."""
    pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        variants = [
            'golem:apidoc[target="syn_pkg.test_fn"]',
            "golem:apidoc[target='syn_pkg.test_fn']",
            'golem:apidoc["syn_pkg.test_fn"]',
            "golem:apidoc[syn_pkg.test_fn]",
            'golem:apidoc[target="syn_pkg.test_fn", depth="summary"]',
        ]
        for v in variants:
            raw = f"= Page\n\n{v}\n"
            out = apidoc.on_pre_parse(raw_content=raw)
            assert "golem:apidoc" not in out
            assert "test_fn" in out
    finally:
        sys.path.remove(str(tmp_path))


def test_on_pre_parse_missing_symbol_graceful():
    from golem.plugins import apidoc

    raw = '= Missing Page\n\ngolem:apidoc[target="nonexistent_pkg_123.fake_func"]\n'
    out = apidoc.on_pre_parse(raw_content=raw)
    assert "golem:apidoc" not in out
    assert "nonexistent_pkg_123.fake_func" in out


def test_apidoc_cli_subcommand(tmp_path):
    from golem.plugins import apidoc

    pkg_dir = tmp_path / "cli_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""CLI target package."""
def cli_action() -> str:
    """Perform action."""
    return "done"
''',
        encoding="utf-8",
    )

    out_dir = tmp_path / "api_out"

    @click.group()
    def cli():
        pass

    apidoc.golem_add_subcommands(cli)

    runner = CliRunner()
    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        result = runner.invoke(cli, ["apidoc", "cli_pkg", "-o", str(out_dir)])
        assert result.exit_code == 0
        assert out_dir.exists()
        adoc_files = list(out_dir.glob("*.adoc"))
        assert len(adoc_files) >= 1
    finally:
        sys.path.remove(str(tmp_path))


def test_build_engine_integration_with_apidoc(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    dist_dir = tmp_path / "dist"

    doc_text = """= Golem Config Guide

Documentation for configuration:

golem:apidoc[target="golem.config.GolemConfig"]
"""
    (content_dir / "index.adoc").write_text(doc_text, encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(dist_dir),
        plugins=["golem.plugins.apidoc"],
    )

    engine = BuildEngine(config)
    engine.build_site()

    out_html = (dist_dir / "index.html").read_text(encoding="utf-8")
    assert "Golem Config Guide" in out_html
    assert "GolemConfig" in out_html
    assert "site_title" in out_html


def test_format_attribute_and_module_attributes(tmp_path):
    """Verify format_attribute() and format_module() rendering of module-level attributes."""
    import sys
    from golem.plugins.apidoc.core.extractor import create_griffe_loader, resolve_symbol
    from golem.plugins.apidoc.core.formatter import format_attribute, format_module

    mod_dir = tmp_path / "attrs_pkg"
    mod_dir.mkdir()
    (mod_dir / "__init__.py").write_text(
        '''"""Constants and configuration attributes."""

API_VERSION: str = "2.0.0"
"""Current API version string."""

MAX_RETRIES: int = 5
"""Maximum number of HTTP retries."""

LONG_DESCRIPTION: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"""A very long constant value."""

UNANNOTATED_VAR = "some_val"

EMPTY_DOC_VAR: float = 3.14

class ServiceConfig:
    """Service configuration class."""
    timeout: int = 30
    """Request timeout in seconds."""
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        loader = create_griffe_loader([tmp_path])
        mod_obj = resolve_symbol(loader, "attrs_pkg")

        # Test format_module() output contains Module Attributes heading and description list
        mod_adoc = format_module(mod_obj, depth="all", heading_level=1)
        assert "= attrs_pkg" in mod_adoc
        assert "== Module Attributes" in mod_adoc
        assert "`API_VERSION`:: (str)" in mod_adoc
        assert "Current API version string." in mod_adoc
        assert 'Default value: `"2.0.0"`' in mod_adoc or "2.0.0" in mod_adoc

        assert "`MAX_RETRIES`:: (int)" in mod_adoc
        assert "Maximum number of HTTP retries." in mod_adoc
        assert "Default value: `5`" in mod_adoc

        assert "`LONG_DESCRIPTION`:: (str)" in mod_adoc
        assert "(truncated; see source)" in mod_adoc

        # Test format_attribute() directly on single attribute
        attr_obj = resolve_symbol(loader, "attrs_pkg.API_VERSION")
        attr_adoc = format_attribute(attr_obj, heading_level=2)
        assert "== API_VERSION" in attr_adoc
        assert '[source,python]\n----\nAPI_VERSION: str = "2.0.0"\n----' in attr_adoc or "API_VERSION: str" in attr_adoc
        assert "Current API version string." in attr_adoc

        # Test format_attribute without annotation
        raw_attr = resolve_symbol(loader, "attrs_pkg.UNANNOTATED_VAR")
        raw_adoc = format_attribute(raw_attr, heading_level=3)
        assert "=== UNANNOTATED_VAR" in raw_adoc
        assert "UNANNOTATED_VAR" in raw_adoc
    finally:
        sys.path.remove(str(tmp_path))


def test_on_pre_parse_verbatim_and_backtick_protection():
    """Verify on_pre_parse does not expand macros in backticks or verbatim blocks."""
    from golem.plugins import apidoc

    raw = """= Guide

Here is `golem:apidoc[...]` in an inline code span.

[source,asciidoc]
----
= Code Listing
golem:apidoc[target="some.pkg.Class", depth="all"]
----

....
golem:apidoc[literal_block]
....

And \\golem:apidoc[target="escaped"] is escaped.
"""
    processed = apidoc.on_pre_parse(raw)

    # Inline backticks preserved
    assert "`golem:apidoc[...]`" in processed

    # Verbatim blocks preserved without expansion or warnings
    assert 'golem:apidoc[target="some.pkg.Class", depth="all"]' in processed
    assert "golem:apidoc[literal_block]" in processed

    # Escaped macro unescaped
    assert 'golem:apidoc[target="escaped"]' in processed
    assert "\\golem:apidoc" not in processed
