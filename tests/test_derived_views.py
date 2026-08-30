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
    # Check that ASG tab contains JSON
    assert '"name"' in html and ('"document"' in html or '"admonition"' in html)
    # Check that HTML tab contains HTML source
    assert '&lt;div class="admonitionblock note"&gt;' in html or '<div class="admonitionblock note">' in html
    # Check that Preview tab contains live rendered HTML
    assert '<div class="admonitionblock note">' in html


def test_zero_js_baseline():
    """Verify zero-JS baseline: first tab is active/visible, subsequent tabs are hidden."""
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
    # First tab button active
    assert 'class="tab-btn active" data-tab="source" role="tab" aria-selected="true" tabindex="0"' in html
    # Subsequent tab buttons inactive
    assert 'class="tab-btn" data-tab="asg" role="tab" aria-selected="false" tabindex="-1"' in html
    assert 'class="tab-btn" data-tab="html" role="tab" aria-selected="false" tabindex="-1"' in html
    assert 'class="tab-btn" data-tab="preview" role="tab" aria-selected="false" tabindex="-1"' in html

    # First tab pane active and not hidden
    assert '<div class="tab-pane active" data-tab="source" role="tabpanel">' in html
    # Subsequent tab panes have hidden attribute
    assert '<div class="tab-pane" data-tab="asg" role="tabpanel" hidden="hidden">' in html
    assert '<div class="tab-pane" data-tab="html" role="tabpanel" hidden="hidden">' in html
    assert '<div class="tab-pane" data-tab="preview" role="tabpanel" hidden="hidden">' in html


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
    assert '"name"' in v_asg["content"]

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
