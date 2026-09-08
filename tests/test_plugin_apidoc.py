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


def test_on_pre_parse_verbatim_and_backtick_protection(caplog):
    """Verify on_pre_parse does not expand macros in backticks or verbatim blocks, and does not warn."""
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
    with caplog.at_level("WARNING", logger="golem.plugins.apidoc"):
        processed = apidoc.on_pre_parse(raw)

    # Inline backticks preserved
    assert "`golem:apidoc[...]`" in processed

    # Verbatim blocks preserved without expansion or warnings
    assert 'golem:apidoc[target="some.pkg.Class", depth="all"]' in processed
    assert "golem:apidoc[literal_block]" in processed

    # Escaped macro unescaped
    assert 'golem:apidoc[target="escaped"]' in processed
    assert "\\golem:apidoc" not in processed

    # No deprecation warning emitted when only inert/escaped/verbatim mentions exist
    assert "on_pre_parse macro expansion in golem.plugins.apidoc is deprecated" not in caplog.text


def test_on_asg_created_macro_replacement(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

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
        ast = asciidoctrine.parse_to_ast(raw_doc)
        resolver = ASGResolver(ast)
        asg = resolver.resolve(ast)

        # Apply on_asg_created hook
        asg = apidoc.on_asg_created(asg=asg)

        # Render HTML from modified ASG
        html = render_body(asg)
        assert "golem:apidoc" not in html
        assert "multiply" in html
        assert "Multiply two numbers." in html
        assert "Here is our multiply function:" in html
        assert "And more content." in html
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_syntax_variants(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

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
            ast = asciidoctrine.parse_to_ast(raw)
            resolver = ASGResolver(ast)
            asg = resolver.resolve(ast)

            asg = apidoc.on_asg_created(asg=asg)
            html = render_body(asg)
            assert "golem:apidoc" not in html
            assert "test_fn" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_missing_symbol_graceful():
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    raw = '= Missing Page\n\ngolem:apidoc[target="nonexistent_pkg_123.fake_func"]\n'
    ast = asciidoctrine.parse_to_ast(raw)
    resolver = ASGResolver(ast)
    asg = resolver.resolve(ast)

    asg = apidoc.on_asg_created(asg=asg)
    html = render_body(asg)
    assert "golem:apidoc" not in html
    assert "nonexistent_pkg_123.fake_func" in html
    assert "admonitionblock warning" in html


def test_on_asg_created_preserves_sections_and_surrounding_blocks(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    pkg_dir = tmp_path / "sect_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Section test package."""
class Worker:
    """Worker class docstring."""
    def perform(self) -> None:
        """Perform action."""
        pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Main Document

Initial overview text.

== Section One

Section one intro.

golem:apidoc[target="sect_pkg.Worker"]

Section one outro.

== Section Two

Section two text.
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        resolver = ASGResolver(ast)
        asg = resolver.resolve(ast)

        # Apply on_asg_created
        asg = apidoc.on_asg_created(asg=asg)

        html = render_body(asg)
        assert "Initial overview text." in html
        assert "Section One" in html
        assert "Section one intro." in html
        assert "Worker" in html
        assert "Worker class docstring." in html
        assert "Section one outro." in html
        assert "Section Two" in html
        assert "Section two text." in html

        # Verify ordering of sections and content
        idx_intro = html.index("Section one intro.")
        idx_worker = html.index("Worker class docstring.")
        idx_outro = html.index("Section one outro.")
        idx_sect2 = html.index("Section Two")
        assert idx_intro < idx_worker < idx_outro < idx_sect2
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_heading_offset(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    pkg_dir = tmp_path / "offset_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Offset package."""
def helper() -> None:
    """Helper function."""
    pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Offset Doc

golem:apidoc[target="offset_pkg.helper", heading_level_offset=1]
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        resolver = ASGResolver(ast)
        asg = resolver.resolve(ast)

        asg = apidoc.on_asg_created(asg=asg)
        html = render_body(asg)
        assert "helper" in html
        # With heading_level_offset=1, function renders as h3 instead of h2
        assert "<h3" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_splices_paragraph_macro(monkeypatch):
    from golem.plugins import apidoc

    fake_nodes = [
        {
            "name": "section",
            "type": "block",
            "title": [{"name": "text", "value": "Fake Module"}],
        },
        {
            "name": "paragraph",
            "type": "block",
            "inlines": [{"name": "text", "value": "Doc content"}],
        },
    ]
    monkeypatch.setattr("golem.plugins.apidoc._expand_macro_target", lambda target: fake_nodes)

    asg = {
        "name": "document",
        "type": "block",
        "blocks": [
            {
                "name": "paragraph",
                "type": "block",
                "inlines": [
                    {
                        "name": "text",
                        "type": "string",
                        "value": 'golem:apidoc[target="some.pkg"]',
                    }
                ],
            }
        ],
    }
    result = apidoc.on_asg_created(asg)
    assert result["blocks"] == fake_nodes


def test_on_asg_created_preserves_surrounding_blocks(monkeypatch):
    from golem.plugins import apidoc

    fake_nodes = [{"name": "section", "type": "block", "title": "Injected Section"}]
    monkeypatch.setattr("golem.plugins.apidoc._expand_macro_target", lambda target: fake_nodes)

    before_block = {
        "name": "paragraph",
        "type": "block",
        "inlines": [{"name": "text", "value": "Before"}],
    }
    after_block = {
        "name": "paragraph",
        "type": "block",
        "inlines": [{"name": "text", "value": "After"}],
    }
    asg = {
        "name": "document",
        "type": "block",
        "blocks": [
            before_block,
            {
                "name": "paragraph",
                "type": "block",
                "inlines": [{"name": "text", "value": 'golem:apidoc[target="some.pkg"]'}],
            },
            after_block,
        ],
    }
    result = apidoc.on_asg_created(asg)
    assert len(result["blocks"]) == 3
    assert result["blocks"][0] == before_block
    assert result["blocks"][1] == fake_nodes[0]
    assert result["blocks"][2] == after_block


def test_on_asg_created_noop_without_macros():
    import copy
    from golem.plugins import apidoc

    asg = {
        "name": "document",
        "type": "block",
        "blocks": [
            {
                "name": "paragraph",
                "type": "block",
                "inlines": [{"name": "text", "value": "Hello world"}],
            },
            {
                "name": "section",
                "type": "block",
                "blocks": [
                    {
                        "name": "paragraph",
                        "type": "block",
                        "inlines": [{"name": "text", "value": "Inner paragraph"}],
                    }
                ],
            },
        ],
    }
    orig = copy.deepcopy(asg)
    result = apidoc.on_asg_created(asg)
    assert result == orig


def test_on_asg_created_nested_section_splicing(monkeypatch):
    from golem.plugins import apidoc

    fake_nodes = [
        {
            "name": "paragraph",
            "type": "block",
            "inlines": [{"name": "text", "value": "Spliced in section"}],
        }
    ]
    monkeypatch.setattr("golem.plugins.apidoc._expand_macro_target", lambda target: fake_nodes)

    asg = {
        "name": "document",
        "type": "block",
        "blocks": [
            {
                "name": "section",
                "type": "block",
                "blocks": [
                    {
                        "name": "paragraph",
                        "type": "block",
                        "inlines": [{"name": "text", "value": "Section Header"}],
                    },
                    {
                        "name": "paragraph",
                        "type": "block",
                        "inlines": [{"name": "text", "value": 'golem:apidoc[target="nested.pkg"]'}],
                    },
                ],
            }
        ],
    }
    result = apidoc.on_asg_created(asg)
    section_blocks = result["blocks"][0]["blocks"]
    assert len(section_blocks) == 2
    assert section_blocks[0]["inlines"][0]["value"] == "Section Header"
    assert section_blocks[1] == fake_nodes[0]


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


def test_on_asg_created_verbatim_and_backtick_protection():
    """Verify on_asg_created does not expand macros in backticks or verbatim blocks."""
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

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
    ast = asciidoctrine.parse_to_ast(raw)
    resolver = ASGResolver(ast)
    asg = resolver.resolve(ast)

    asg = apidoc.on_asg_created(asg=asg)
    html = render_body(asg)

    # Inline backticks preserved
    assert "golem:apidoc[...]" in html

    # Verbatim blocks preserved without expansion or warnings
    assert 'golem:apidoc[target="some.pkg.Class", depth="all"]' in html
    assert "golem:apidoc[literal_block]" in html

    # Escaped macro unescaped
    assert 'golem:apidoc[target="escaped"]' in html
    assert "\\golem:apidoc" not in html


def test_apidoc_format_composite_types(tmp_path):
    from golem.plugins import apidoc
    import sys

    pkg_dir = tmp_path / "typed_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Typed module."""
from typing import Union, Optional

def process_data(data: Union[dict[str, int], list[str]], timeout: Optional[float] = None) -> dict[str, Any]:
    """Process incoming data payload.

    Args:
        data (dict[str, int] or list[str]): Input payload.
        timeout (float, optional): Optional timeout in seconds. Defaults to 1.0.

    Returns:
        result (dict[str, Any]): Processed result mapping.
    """
    return {}
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Typed Guide

golem:apidoc[target="typed_pkg.process_data"]
"""
        res = apidoc.on_pre_parse(raw_content=raw_doc)
        assert "process_data" in res
        assert "data" in res
        assert "timeout" in res

        # Verify signature has composite and optional types
        assert (
            "def process_data(data: Union[dict[str, int], list[str]], timeout: Optional[float] = None) -> dict[str, Any]:"
            in res
        )

        # Verify docstring parameter composite type conversion
        assert "`data`:: (dict[str, int] or list[str]) Input payload." in res
        assert "`timeout`:: (float, optional) Optional timeout in seconds." in res

        # Verify docstring named return value and composite return type
        assert "`result` (dict[str, Any]):: Processed result mapping." in res
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_format_docstring_composite_types_and_named_returns():
    from golem.plugins.apidoc.core.formatter import format_docstring

    doc = """Process incoming data payload.

Args:
    payload (Union[dict[str, int], list[str]]): Input payload data.
    timeout (Optional[float]): Optional timeout in seconds.

Returns:
    result (dict[str, Any]): Processed result mapping.

Yields:
    item (Union[str, int]): Streamed progress item.
"""
    adoc = format_docstring(doc, style="google")
    assert "[parameters]" in adoc
    assert "`payload`:: (Union[dict[str, int], list[str]]) Input payload data." in adoc
    assert "`timeout`:: (Optional[float]) Optional timeout in seconds." in adoc
    assert "[returns]" in adoc
    assert "`result` (dict[str, Any]):: Processed result mapping." in adoc
    assert "[yields]" in adoc
    assert "`item` (Union[str, int]):: Streamed progress item." in adoc


def test_on_asg_created_composite_types(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body
    import sys

    pkg_dir = tmp_path / "asg_typed_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Typed module."""
from typing import Union, Optional

def process_data(data: Union[dict[str, int], list[str]], timeout: Optional[float] = None) -> dict[str, Any]:
    """Process incoming data payload.

    Args:
        data (dict[str, int] or list[str]): Input payload.
        timeout (float, optional): Optional timeout in seconds. Defaults to 1.0.

    Returns:
        result (dict[str, Any]): Processed result mapping.
    """
    return {}
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Typed Guide

golem:apidoc[target="asg_typed_pkg.process_data"]
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        asg = ASGResolver(ast).resolve(ast)
        spliced_asg = apidoc.on_asg_created(asg=asg)
        html = render_body(spliced_asg)
        assert "process_data" in html
        assert "dict[str, int]" in html
        assert "result" in html
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_format_docstring_defensive_fallback():
    from unittest.mock import patch
    import pytest
    from golem.plugins.apidoc.core.formatter import format_docstring

    doc = "Some plain text docstring."
    # If griffe.parse raises an exception, it propagates directly
    with patch("griffe.parse", side_effect=RuntimeError("Parsing error")):
        with pytest.raises(RuntimeError, match="Parsing error"):
            format_docstring(doc)

    # If asciidocstring.griffe_bridge.to_asciidoc raises an exception, it propagates directly
    with patch("asciidocstring.griffe_bridge.to_asciidoc", side_effect=RuntimeError("Bridge error")):
        with pytest.raises(RuntimeError, match="Bridge error"):
            format_docstring(doc)

    # If to_asciidoc returns empty string or whitespace for non-empty docstring, fall back to raw
    with patch("asciidocstring.griffe_bridge.to_asciidoc", return_value=""):
        res = format_docstring(doc)
        assert res == "Some plain text docstring."

    with patch("asciidocstring.griffe_bridge.to_asciidoc", return_value="   \n\t  "):
        res = format_docstring(doc)
        assert res == "Some plain text docstring."


def test_format_docstring_style_variants():
    import griffe
    from golem.plugins.apidoc.core.formatter import format_docstring

    doc = """Process data.

Args:
    x (int): Value.
"""
    # Parser enum
    res1 = format_docstring(doc, style=griffe.Parser.google)
    assert "[parameters]" in res1
    assert "`x`:: (int) Value." in res1

    # Uppercase string
    res2 = format_docstring(doc, style="GOOGLE")
    assert "[parameters]" in res2
    assert "`x`:: (int) Value." in res2


def test_on_build_start_is_registered_hookimpl():
    """Verify on_build_start is defined and registered as a hookimpl in the apidoc plugin."""
    from golem.plugins import apidoc, get_plugin_manager

    assert hasattr(apidoc, "on_build_start")
    pm = get_plugin_manager()
    pm.register(apidoc)
    hookimpls = pm.hook.on_build_start.get_hookimpls()
    apidoc_impls = [h for h in hookimpls if h.plugin is apidoc]
    assert len(apidoc_impls) == 1
    assert apidoc_impls[0].function == apidoc.on_build_start


def test_on_build_start_invokes_generate_api_docs_when_configured(tmp_path, monkeypatch):
    """Verify calling on_build_start with api_packages invokes generate_api_docs with expected args."""
    from pathlib import Path
    from golem.plugins import apidoc

    calls = []

    def mock_generate_api_docs(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(apidoc, "generate_api_docs", mock_generate_api_docs)

    config = GolemConfig(
        content_dir=str(tmp_path / "docs"),
        api_packages=["mypackage", "otherpackage"],
        api_output_dir="reference",
        api_docstring_style="sphinx",
    )

    apidoc.on_build_start(config)

    assert len(calls) == 1
    assert calls[0]["packages"] == ["mypackage", "otherpackage"]
    assert calls[0]["output_dir"] == tmp_path / "docs" / "reference"
    assert calls[0]["docstring_style"] == "sphinx"
    assert any(str(p) == str(Path.cwd()) for p in calls[0]["search_paths"])


def test_on_build_start_noop_when_api_packages_unset_or_empty(tmp_path, monkeypatch):
    """Verify calling on_build_start does nothing if api_packages is None or empty."""
    from golem.plugins import apidoc

    calls = []

    def mock_generate_api_docs(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(apidoc, "generate_api_docs", mock_generate_api_docs)

    # When empty list
    config_empty = GolemConfig(content_dir=str(tmp_path / "docs"), api_packages=[])
    apidoc.on_build_start(config_empty)
    assert len(calls) == 0

    # When None
    class ConfigNone:
        content_dir = str(tmp_path / "docs")
        api_packages = None

    apidoc.on_build_start(ConfigNone())
    assert len(calls) == 0


def test_on_build_start_error_handling(tmp_path, monkeypatch, caplog):
    """Verify on_build_start error handling in non-strict and strict modes."""
    import logging
    import pytest
    from golem.plugins import apidoc, GolemBuildAbortError

    def failing_generate_api_docs(**kwargs):
        raise RuntimeError("Generation failed boom")

    monkeypatch.setattr(apidoc, "generate_api_docs", failing_generate_api_docs)

    # Non-strict mode: logs warning, does not raise
    config_lenient = GolemConfig(
        content_dir=str(tmp_path / "docs"),
        api_packages=["some_pkg"],
        strict=False,
    )
    with caplog.at_level(logging.WARNING, logger="golem.plugins.apidoc"):
        apidoc.on_build_start(config_lenient)
    assert "Failed to generate API documentation during build: Generation failed boom" in caplog.text

    # Strict mode: raises GolemBuildAbortError
    config_strict = GolemConfig(
        content_dir=str(tmp_path / "docs"),
        api_packages=["some_pkg"],
        strict=True,
    )
    with pytest.raises((GolemBuildAbortError, RuntimeError)):
        apidoc.on_build_start(config_strict)


def test_build_engine_integration_api_packages(tmp_path):
    """End-to-end integration: BuildEngine generates and compiles API docs when api_packages is configured."""
    import sys

    pkg_dir = tmp_path / "e2e_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""E2E Package docstring."""
def calculate(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: First number.
        b: Second number.

    Returns:
        Sum of a and b.
    """
    return a + b
''',
        encoding="utf-8",
    )

    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Home\n\nWelcome home.", encoding="utf-8")

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["golem.plugins.apidoc"],
        api_packages=["e2e_pkg"],
        api_output_dir="api",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        engine = BuildEngine(config)
        compiled = engine.build_site()

        # Check .adoc was generated in content_dir / api
        generated_adoc = content_dir / "api" / "e2e_pkg.adoc"
        assert generated_adoc.exists()

        # Check HTML was generated in output_dir / api
        generated_html = output_dir / "api" / "e2e_pkg.html"
        assert generated_html.exists()
        assert generated_html in compiled

        html_text = generated_html.read_text(encoding="utf-8")
        assert "E2E Package" in html_text or "e2e_pkg" in html_text
        assert "calculate" in html_text
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
