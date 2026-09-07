"""Tests for golem.views, golem.views_protocol, and circular import elimination."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from golem.renderer import render_body
from golem.views import (
    extract_listing_views,
    generate_asciidoc_views,
    parse_views_attribute,
)
from golem.views_protocol import (
    BodyRendererProtocol,
    extract_plain_text,
    get_default_renderer,
    set_default_renderer,
)


def test_top_level_import_order_views_first() -> None:
    """Verify importing golem.views before golem.renderer succeeds without circular import errors."""
    code = "import sys; import golem.views; import golem.renderer; sys.stdout.write('SUCCESS')"
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert res.stdout == "SUCCESS"
    assert "ImportError" not in res.stderr
    assert "circular" not in res.stderr.lower()


def test_top_level_import_order_renderer_first() -> None:
    """Verify importing golem.renderer before golem.views succeeds without circular import errors."""
    code = "import sys; import golem.renderer; import golem.views; sys.stdout.write('SUCCESS')"
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert res.stdout == "SUCCESS"
    assert "ImportError" not in res.stderr
    assert "circular" not in res.stderr.lower()


def test_views_module_has_no_import_of_renderer() -> None:
    """Verify golem.views module does not import golem.renderer directly at top or function level."""
    import inspect
    import golem.views

    src = inspect.getsource(golem.views)
    assert "from golem.renderer" not in src
    assert "import golem.renderer" not in src


def test_extract_listing_views_explicit_renderer() -> None:
    """Verify extract_listing_views works with explicit renderer parameter."""
    node = {
        "name": "listing",
        "value": "WARNING: Caution advised.",
        "attributes": {
            "language": "asciidoc",
            "render": "source,preview",
        },
    }
    views = extract_listing_views(node, renderer=render_body)
    assert len(views) == 2
    assert views[0]["id"] == "source"
    assert views[1]["id"] == "preview"
    assert "admonitionblock warning" in views[1]["content"]


def test_extract_listing_views_explicit_renderer_func() -> None:
    """Verify extract_listing_views works with explicit renderer_func parameter."""
    node = {
        "name": "listing",
        "value": "TIP: Pro tip here.",
        "attributes": {
            "language": "asciidoc",
            "render": "source,html",
        },
    }
    views = extract_listing_views(node, renderer_func=render_body)
    assert len(views) == 2
    assert views[0]["id"] == "source"
    assert views[1]["id"] == "html"
    assert "admonitionblock tip" in views[1]["content"]


def test_extract_listing_views_fallback_without_renderer() -> None:
    """Verify extract_listing_views falls back cleanly when no renderer is registered."""
    original_default = get_default_renderer()
    try:
        # Temporarily clear default renderer
        set_default_renderer(None)  # type: ignore[arg-type]
        node = {
            "name": "listing",
            "value": "NOTE: Fallback test.",
            "attributes": {
                "language": "asciidoc",
                "render": "source,preview",
            },
        }
        views = extract_listing_views(node, renderer=None, renderer_func=None)
        assert len(views) == 2
        assert views[0]["id"] == "source"
        assert views[1]["id"] == "preview"
        assert '<div class="rendered-preview">' in views[1]["content"]
    finally:
        if original_default is not None:
            set_default_renderer(original_default)


def test_custom_body_renderer_protocol_compliance() -> None:
    """Verify custom callable implementing BodyRendererProtocol renders as expected."""

    def custom_renderer(asg_root: Any, search_paths: Any = None, highlighter: Any = None) -> str:
        return '<div class="custom-render">Custom Output</div>'

    assert isinstance(custom_renderer, BodyRendererProtocol)

    node = {
        "name": "listing",
        "value": "custom listing text",
        "attributes": {
            "language": "asciidoc",
            "render": "preview",
        },
    }
    views = extract_listing_views(node, renderer=custom_renderer)
    assert len(views) == 1
    assert views[0]["id"] == "preview"
    assert '<div class="custom-render">Custom Output</div>' in views[0]["content"]


def test_derived_view_tabs_compile_and_render_full_cycle() -> None:
    """Verify full compilation and rendering of derived view tabs without circular warnings."""
    asg = {
        "name": "listing",
        "type": "block",
        "title": "Admonition Example",
        "value": "NOTE: Testing full cycle tabs.",
        "attributes": {
            "language": "asciidoc",
            "render": "source,asg,html,preview",
        },
    }
    html = render_body(asg)
    assert 'class="listingblock multi-view"' in html
    assert 'role="tablist"' in html
    assert 'data-tab="source"' in html
    assert 'data-tab="asg"' in html
    assert 'data-tab="html"' in html
    assert 'data-tab="preview"' in html
    assert '<div class="tab-pane active" data-tab="source" role="tabpanel">' in html
    assert '<div class="tab-pane" data-tab="preview" role="tabpanel">' in html


def test_views_protocol_extract_plain_text() -> None:
    """Verify extract_plain_text handles strings, lists, dicts, and nested inline hierarchies."""
    assert extract_plain_text("") == ""
    assert extract_plain_text("raw text") == "raw text"
    assert extract_plain_text(["hello", " ", "world"]) == "hello world"
    assert extract_plain_text({"name": "text", "value": "node value"}) == "node value"
    assert extract_plain_text({"text": "dict text"}) == "dict text"
    assert extract_plain_text({"inlines": [{"name": "text", "value": "nested"}]}) == "nested"


def test_extract_listing_views_with_inlines_fallback() -> None:
    """Verify extract_listing_views extracts code_text from inlines when value is None."""
    node = {
        "name": "listing",
        "value": None,
        "inlines": [
            {"name": "text", "value": "NOTE: Extracted from inlines."},
        ],
        "attributes": {
            "language": "asciidoc",
            "render": "source,preview",
        },
    }
    views = extract_listing_views(node, renderer=render_body)
    assert len(views) == 2
    assert "Extracted from inlines" in views[0]["content"]


def test_parse_views_attribute() -> None:
    """Verify parse_views_attribute parses alias keys and returns canonical list."""
    assert parse_views_attribute({"render": "source,preview"}) == ["source", "preview"]
    assert parse_views_attribute({"views": "adoc,ast,markup"}) == ["source", "asg", "html"]
    assert parse_views_attribute(None) == []


def test_generate_asciidoc_views_with_explicit_renderer() -> None:
    """Verify generate_asciidoc_views accepts explicit renderer without circular imports."""
    views = generate_asciidoc_views("NOTE: Generated note.", ["source", "preview"], renderer=render_body)
    assert len(views) == 2
    assert views[0]["id"] == "source"
    assert views[1]["id"] == "preview"
    assert "admonitionblock note" in views[1]["content"]
