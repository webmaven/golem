"""Tests for AsciiDoc derived multi-view compilation engine."""

from golem.renderer import render_body
from golem.views import (
    generate_asciidoc_views,
    parse_views_attribute,
    extract_listing_views,
)


def test_asciidoc_derived_views_rendering():
    """Verify render='source,asg,html,preview' produces multi-tab container with all four representations."""
    asg = {
        "name": "listing",
        "type": "block",
        "title": "Admonition Example",
        "value": "NOTE: This is a note.",
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
    # Check that ASG tab contains JSON — Pygments HTML-escapes " as &quot; inside spans,
    # so we match the highlighted form rather than raw JSON.
    assert "&quot;name&quot;" in html and ("&quot;document&quot;" in html or "&quot;admonition&quot;" in html)
    # Check that HTML tab contains HTML source
    assert '&lt;div class="admonitionblock note"&gt;' in html or '<div class="admonitionblock note">' in html
    # Check that Preview tab contains live rendered HTML
    assert '<div class="admonitionblock note">' in html


def test_zero_js_baseline():
    """Verify zero-JS baseline: radio inputs control tab selection declaratively via CSS :has()."""
    asg = {
        "name": "listing",
        "type": "block",
        "value": "NOTE: Test zero JS.",
        "attributes": {
            "language": "asciidoc",
            "render": "source,asg,html,preview",
        },
    }
    html = render_body(asg)
    # First tab radio input is checked
    assert 'type="radio"' in html
    assert 'class="tab-input"' in html
    assert 'value="source"' in html
    assert 'checked="checked"' in html

    # Tab labels are present with data-tab and for attributes
    assert 'class="tab-btn active"' in html
    assert 'data-tab="source"' in html
    assert 'data-tab="asg"' in html
    assert 'data-tab="html"' in html
    assert 'data-tab="preview"' in html

    # Tab panes are present with role="tabpanel"
    assert '<div class="tab-pane active" data-tab="source" role="tabpanel">' in html
    assert '<div class="tab-pane" data-tab="asg" role="tabpanel">' in html
    assert '<div class="tab-pane" data-tab="html" role="tabpanel">' in html
    assert '<div class="tab-pane" data-tab="preview" role="tabpanel">' in html


def test_attribute_aliases():
    """Verify attribute aliases (views, display, formats) work identically to render."""
    # Test 'views' attribute
    asg_views = {
        "name": "listing",
        "type": "block",
        "value": "NOTE: Using views attr.",
        "attributes": {
            "language": "asciidoc",
            "views": "source,asg,html,preview",
        },
    }
    html_views = render_body(asg_views)
    assert 'class="listingblock multi-view"' in html_views
    assert 'data-tab="source"' in html_views
    assert 'data-tab="asg"' in html_views

    # Test 'display' attribute
    asg_display = {
        "name": "listing",
        "type": "block",
        "value": "NOTE: Using display attr.",
        "attributes": {
            "language": "asciidoc",
            "display": "source,preview",
        },
    }
    html_display = render_body(asg_display)
    assert 'class="listingblock multi-view"' in html_display
    assert 'data-tab="source"' in html_display
    assert 'data-tab="preview"' in html_display
    assert 'data-tab="asg"' not in html_display
    assert 'data-tab="html"' not in html_display

    # Test 'formats' attribute
    asg_formats = {
        "name": "listing",
        "type": "block",
        "value": "NOTE: Using formats attr.",
        "attributes": {
            "language": "asciidoc",
            "formats": "html,preview",
        },
    }
    html_formats = render_body(asg_formats)
    assert 'class="listingblock multi-view"' in html_formats
    assert 'data-tab="html"' in html_formats
    assert 'data-tab="preview"' in html_formats
    assert 'data-tab="source"' not in html_formats


def test_subset_views():
    """Verify subset views synthesis (e.g. render='source,preview')."""
    asg = {
        "name": "listing",
        "type": "block",
        "title": "Preview Only Snippet",
        "value": "IMPORTANT: Be careful!",
        "attributes": {
            "language": "asciidoc",
            "render": "source,preview",
        },
    }
    html = render_body(asg)
    assert 'class="listingblock multi-view"' in html
    assert 'data-tab="source"' in html
    assert 'data-tab="preview"' in html
    assert 'data-tab="asg"' not in html
    assert 'data-tab="html"' not in html
    assert "admonitionblock important" in html


def test_standard_listing_unmodified():
    """Verify standard listing without render attribute renders normally without tabs."""
    asg = {
        "name": "listing",
        "type": "block",
        "title": "Standard Listing",
        "value": "print('hello')",
        "attributes": {
            "language": "python",
        },
    }
    html = render_body(asg)
    assert 'class="listingblock"' in html
    assert "multi-view" not in html
    assert 'role="tablist"' not in html
    assert "data-tab" not in html
    assert "language-python" in html


def test_parse_views_attribute():
    """Verify parse_views_attribute utility parses strings, lists, and aliases."""
    assert parse_views_attribute({"render": "source, asg, html, preview"}) == ["source", "asg", "html", "preview"]
    assert parse_views_attribute({"views": "adoc, ast, markup, view"}) == ["source", "asg", "html", "preview"]
    assert parse_views_attribute({"display": ["source", "preview"]}) == ["source", "preview"]
    assert parse_views_attribute({"formats": "html"}) == ["html"]
    assert parse_views_attribute({}) == []
    assert parse_views_attribute(None) == []


def test_generate_asciidoc_views_direct():
    """Verify generate_asciidoc_views produces valid view dicts with expected keys."""
    views = generate_asciidoc_views("NOTE: Direct test.", ["source", "asg", "html", "preview"])
    assert len(views) == 4

    v_source = views[0]
    assert v_source["id"] == "source"
    assert v_source["label"] == "AsciiDoc"
    assert "NOTE: Direct test." in v_source["content"]

    v_asg = views[1]
    assert v_asg["id"] == "asg"
    assert v_asg["label"] == "ASG"
    assert "&quot;name&quot;" in v_asg["content"]  # Pygments escapes " as &quot; in highlighted JSON

    v_html = views[2]
    assert v_html["id"] == "html"
    assert v_html["label"] == "HTML"
    assert "admonitionblock note" in v_html["content"]

    v_preview = views[3]
    assert v_preview["id"] == "preview"
    assert v_preview["label"] == "Preview"
    assert '<div class="rendered-preview">' in v_preview["content"]
    assert "admonitionblock note" in v_preview["content"]


def test_extract_listing_views():
    """Verify extract_listing_views extracts views from ASG listing node."""
    node = {
        "name": "listing",
        "value": "WARNING: Danger zone!",
        "attributes": {
            "language": "asciidoc",
            "render": "source,preview",
        },
    }
    views = extract_listing_views(node)
    assert len(views) == 2
    assert views[0]["id"] == "source"
    assert views[1]["id"] == "preview"

    # Node without render attribute returns empty list
    plain_node = {
        "name": "listing",
        "value": "plain text",
    }
    assert extract_listing_views(plain_node) == []


def test_snippet_parsing_file_inclusion_safety():
    """Verify AsciiDoc snippet containing include directives is parsed safely without file inclusion."""
    snippet_missing = "include::nonexistent_file_xyz_123.adoc[]\n\nNOTE: Safe text."
    views_missing = generate_asciidoc_views(snippet_missing, ["source", "asg", "html", "preview"])
    assert len(views_missing) == 4
    # Ensure ASG dict does not contain an inclusion failure / crash error
    asg_view = next(v for v in views_missing if v["id"] == "asg")
    assert "error" not in asg_view["content"].lower() or "include" not in asg_view["content"].lower()
    # Preview should render without crashing
    preview_view = next(v for v in views_missing if v["id"] == "preview")
    assert "Safe text." in preview_view["content"]

    snippet_passwd = "include::/etc/passwd[]\n\nWARNING: Security check."
    views_passwd = generate_asciidoc_views(snippet_passwd, ["source", "asg", "html", "preview"])
    assert len(views_passwd) == 4
    preview_passwd = next(v for v in views_passwd if v["id"] == "preview")
    # Must not contain contents of /etc/passwd (e.g. root:x:0:0)
    assert "root:x:0:0" not in preview_passwd["content"]
    assert "root:*:" not in preview_passwd["content"]


def test_nested_rendered_listings_recursion_guard():
    """Verify nested listings with render attributes do not trigger infinite recursion."""
    nested_adoc = '[source,asciidoc]\n[render="source,preview"]\n----\nNOTE: Inner note\n----\n'
    asg = {
        "name": "listing",
        "type": "block",
        "title": "Outer Listing",
        "value": nested_adoc,
        "attributes": {
            "language": "asciidoc",
            "render": "source,preview",
        },
    }
    # Should render cleanly without infinite recursion
    html = render_body(asg)
    assert 'class="listingblock multi-view"' in html
    assert 'data-tab="source"' in html
    assert 'data-tab="preview"' in html
    assert "Inner note" in html


def test_template_hygiene_no_inline_import():
    """Verify listing.html template does not use __import__."""
    from pathlib import Path

    tpl_path = Path(__file__).parent.parent / "src" / "golem" / "templates" / "default" / "listing.html"
    tpl_content = tpl_path.read_text(encoding="utf-8")
    assert "__import__" not in tpl_content


def test_include_directive_in_snippet_is_not_resolved():
    """Verify that include directives in AsciiDoc snippets are NOT resolved during view derivation."""
    snippet = "include::/etc/passwd[]"
    views = generate_asciidoc_views(snippet, ["source", "asg", "html"])
    # Should produce views without raising PreprocessorError or reading local files
    assert len(views) == 3
    # The ASG view should not contain file system contents
    asg_view = next((v for v in views if v["id"] == "asg"), None)
    assert asg_view is not None
    assert "/etc/passwd" not in asg_view["content"] or "include" in asg_view["content"]


def test_nested_render_attribute_does_not_recurse():
    """Verify that a snippet containing another render-attributed listing does not cause infinite recursion."""
    snippet = '[source,asciidoc,render="source,html"]\n----\nhello\n----'
    views = generate_asciidoc_views(snippet, ["html", "preview"])
    assert len(views) == 2
    # Should complete without RecursionError or stack overflow
