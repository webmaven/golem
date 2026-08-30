from pathlib import Path
import asciidoctrine
from asciidoctrine.resolver import ASGResolver
from golem.renderer import render_body, generate_toc_html


def test_html_generation():
    adoc_source = """
= Main Document Header

This is a premier paragraph with *bold* text.

[source,python]
----
import sys
print(sys.version)
----
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    resolver = ASGResolver(ast)
    asg = resolver.resolve(ast)
    html = render_body(asg)
    assert "This is a premier paragraph with <strong>bold</strong> text" in html
    assert '<pre class="highlight python"><code class="language-python">' in html
    assert '<span class="kn">import</span>' in html
    assert '<span class="nn">sys</span>' in html


def test_html_listing_escaping():
    adoc_source = """
[source,python]
----
html = compiler.compile_page("Developer Guide", "<p>Content goes here</p>", "")
----
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    resolver = ASGResolver(ast)
    asg = resolver.resolve(ast)
    html_output = render_body(asg)
    # The literal '<p>' should be safely escaped in HTML rendering to '&lt;p&gt;'
    assert "&lt;p&gt;Content goes here&lt;/p&gt;" in html_output
    assert "<p>Content goes here</p>" not in html_output


def test_no_text_corruption():
    adoc_source = """
This is a standard text with 2 * 3 = 6 and a variable_name inside.
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    resolver = ASGResolver(ast)
    asg = resolver.resolve(ast)
    html = render_body(asg)
    assert "2 * 3 = 6" in html
    assert "variable_name" in html
    assert "<strong>" not in html
    assert "<em>" not in html


def test_render_paragraphs_and_headings():
    adoc_source = """
== First Heading

This is a paragraph with *bold*, _italic_, and normal text.

=== Sub Heading

Another paragraph in the subsection.
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert "<h2>First Heading</h2>" in html
    assert "<h3>Sub Heading</h3>" in html
    assert "<p>This is a paragraph with <strong>bold</strong>, <em>italic</em>, and normal text.</p>" in html
    assert "<p>Another paragraph in the subsection.</p>" in html


def test_render_admonitions():
    adoc_source = """
[NOTE]
====
This is a note admonition with *bold* emphasis.
====

[WARNING]
====
Danger ahead!
====
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert "admonitionblock note" in html
    assert "This is a note admonition with <strong>bold</strong> emphasis." in html
    assert "admonitionblock warning" in html
    assert "Danger ahead!" in html


def test_render_listings_with_callouts_and_inlines():
    adoc_source = """
[source,python]
----
def greet(name): # <1>
    print(f"Hello, {name}!") # <2>
----
<1> Define function
<2> Print formatted greeting
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert '<pre class="highlight python"><code class="language-python">' in html
    assert 'data-value="1"' in html
    assert 'data-value="2"' in html
    assert '<ol class="colist">' in html
    assert "Define function" in html
    assert "Print formatted greeting" in html


def test_render_lists_and_checkboxes():
    adoc_source = """
* [x] Task one
* [ ] Task two
* Standard item

. First item
. Second item
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert '<ul class="checklist">' in html or "<ul" in html
    assert "Task one" in html
    assert "Task two" in html
    assert "<ol" in html
    assert "First item" in html


def test_render_description_lists():
    adoc_source = """
Term 1:: Definition for term 1
Term 2::
Definition for term 2 with *bold*.
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert '<dl class="dlist">' in html
    assert "<dt>Term 1</dt>" in html
    assert "Definition for term 1" in html
    assert "<dt>Term 2</dt>" in html
    assert "<strong>bold</strong>" in html


def test_render_tables():
    adoc_source = """
|===
| Header 1 | Header 2

| Row 1 Col 1 | Row 1 Col 2
| Row 2 Col 1 | Row 2 Col 2
|===
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert '<table class="tableblock"' in html
    assert "<td" in html
    assert "Row 1 Col 1" in html
    assert "Row 2 Col 2" in html


def test_render_stem_math():
    adoc_source = """
This is an equation: stem:[E = mc^2]
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert '<span class="stem">E = mc^2</span>' in html


def test_render_footnotes():
    adoc_source = """
A statement with a footnote. footnote:[This is footnote content.]
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert '<sup class="footnote"' in html
    assert '<div id="footnotes">' in html
    assert "This is footnote content." in html


def test_render_body_search_paths_override(tmp_path):
    # Create custom paragraph.html template in search_paths
    custom_tpl = tmp_path / "paragraph.html"
    custom_tpl.write_text(
        '<p class="golem-custom"><tal:block tal:repeat="inline node.get(\'inlines\', [])" tal:replace="structure renderer.render(inline, ctx)" /></p>',
        encoding="utf-8",
    )

    adoc_source = "Custom template override test."
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg, search_paths=[tmp_path])
    assert '<p class="golem-custom">Custom template override test.</p>' in html


def test_render_body_with_ast_node():
    from asciidoctrine.nodes import Paragraph, Text

    node = Paragraph(inlines=[Text("Direct AST node rendering")])
    html = render_body(node)
    assert "<p>Direct AST node rendering</p>" in html


def test_generate_toc_html_from_ast_and_asg():
    from asciidoctrine.nodes import Document, Section, Text

    # From AST Node
    sec1 = Section(level=1, title=[Text("Introduction")])
    sec2 = Section(level=2, title=[Text("Details")])
    doc = Document(blocks=[sec1, sec2])

    toc_html = generate_toc_html(doc)
    assert '<nav class="toc">' in toc_html
    assert '<ul class="toc-list">' in toc_html
    assert '<a href="#introduction">Introduction</a>' in toc_html
    assert '<ul class="toc-level-2">' in toc_html
    assert '<a href="#details">Details</a>' in toc_html
    assert "</nav>" in toc_html

    # Empty document returns empty string
    empty_doc = Document(blocks=[])
    assert generate_toc_html(empty_doc) == ""

    # From resolved ASG dict
    adoc = """
= Document Title

== First Section
Some content.

=== Nested Section
More content.

== Second Section
End content.
"""
    ast = asciidoctrine.parse_to_ast(adoc)
    asg = ASGResolver(ast).resolve(ast)
    toc_asg_html = generate_toc_html(asg)
    assert '<nav class="toc">' in toc_asg_html
    assert '<a href="#first-section">First Section</a>' in toc_asg_html
    assert '<a href="#nested-section">Nested Section</a>' in toc_asg_html
    assert '<a href="#second-section">Second Section</a>' in toc_asg_html


def test_collect_node_types():
    from golem.renderer import collect_node_types

    asg = {
        "name": "document",
        "blocks": [
            {"name": "section", "title": [{"name": "text", "value": "Sec 1"}]},
            {"name": "listing", "language": "python", "value": "print(1)"},
            {"name": "admonition", "style": "NOTE", "blocks": [{"name": "paragraph", "value": "note text"}]},
        ],
    }
    types = collect_node_types(asg)
    assert "document" in types
    assert "section" in types
    assert "listing" in types
    assert "admonition" in types
    assert "paragraph" in types
    assert "text" in types
    assert types == sorted(list(set(types)))


def test_collect_node_types_with_ast_node():
    from asciidoctrine.nodes import Document, Section, Paragraph, Text, Table, TableRow, TableCell
    from golem.renderer import collect_node_types

    doc = Document(
        blocks=[
            Section(
                level=1,
                title=[Text("Sec 1")],
                blocks=[
                    Paragraph(inlines=[Text("Para 1")]),
                    Table(rows=[TableRow(cells=[TableCell(blocks=[Paragraph(inlines=[Text("Cell 1")])])])]),
                ],
            )
        ]
    )
    types = collect_node_types(doc)
    assert "document" in types
    assert "section" in types
    assert "paragraph" in types
    assert "text" in types
    assert "table" in types
    assert "row" in types
    assert "cell" in types
    assert types == sorted(list(set(types)))


def test_render_body_pygments_highlighting():
    adoc_source = """
[source,toml]
----
[site]
title = "My Site"
count = 42
----
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert '<pre class="highlight toml"><code class="language-toml">' in html
    assert (
        '<span class="s">' in html or '<span class="s2">' in html or '<span class="mi">' in html or '<span class="m">' in html
    )


def test_render_body_unknown_language_fallback():
    adoc_source = """
[source,unknownlang]
----
raw unhighlighted code
----
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)
    html = render_body(asg)
    assert "raw unhighlighted code" in html
    assert '<pre class="highlight unknownlang">' in html
    assert "<code" in html


def test_render_body_custom_highlighter():
    adoc_source = """
[source,python]
----
x = 1
----
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    asg = ASGResolver(ast).resolve(ast)

    def custom_highlighter(code: str, lang: str):
        return f'<pre class="custom-{lang}">{code.strip()}</pre>'

    html = render_body(asg, highlighter=custom_highlighter)
    assert '<pre class="custom-python">x = 1</pre>' in html


def test_extract_plain_text_no_duplication():
    from golem.renderer import _extract_plain_text

    adoc_source = """= Document Title

== Section Heading

=== Sub Section
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    assert _extract_plain_text(ast.blocks[0].title) == "Section Heading"
    assert _extract_plain_text(ast.blocks[0].blocks[0].title) == "Sub Section"


def test_toc_html_no_duplicate_titles():
    adoc_source = """= Changelog

== Unreleased

=== Added

=== Fixed

== 0.1.0a2 - 2026-08-24

=== Added

=== Fixed
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    toc_html = generate_toc_html(ast)
    assert '<li class="toc-item level-1"><a href="#unreleased">Unreleased</a>' in toc_html
    assert '<li class="toc-item level-2"><a href="#added">Added</a></li>' in toc_html
    assert '<li class="toc-item level-1"><a href="#0-1-0a2-2026-08-24">0.1.0a2 - 2026-08-24</a>' in toc_html
    assert "UnreleasedUnreleased" not in toc_html
    assert "AddedAdded" not in toc_html


def test_render_listing_header_structure():
    """Verify listing rendering generates semantic listing-header with title, badges, and copy button."""
    asg = {
        "name": "listing",
        "type": "block",
        "title": "sample.py",
        "value": "print('hello')",
        "attributes": {
            "language": "python",
            "role": "test shared",
        },
    }
    html = render_body(asg)
    assert '<figure class="listingblock"' in html
    assert '<header class="listing-header">' in html
    assert '<span class="listing-title">sample.py</span>' in html
    assert 'class="badge badge-test"' in html
    assert 'class="badge badge-shared"' in html
    assert 'class="badge badge-lang">PYTHON</span>' in html
    assert 'class="listing-copy-btn"' in html


def test_listing_copy_button_markup():
    """Verify listing copy button contains accessible aria-label and icon-copy class."""
    asg = {"name": "listing", "type": "block", "value": "x = 1", "attributes": {"language": "python"}}
    html = render_body(asg)
    assert 'aria-label="Copy code to clipboard"' in html
    assert 'class="icon-copy"' in html


def test_listing_role_attribute_sanitization():
    """Verify malformed and malicious role attributes are sanitized to safe CSS class tokens."""
    asg = {
        "name": "listing",
        "type": "block",
        "title": "secure.py",
        "value": "x = 1",
        "attributes": {
            "language": "python",
            "role": 'valid-role safe_role_1 test" onclick="alert(1)" <script>bad</script>',
        },
    }
    html = render_body(asg)
    assert 'class="badge badge-valid-role"' in html
    assert 'class="badge badge-safe_role_1"' in html
    assert "<script>" not in html
    assert 'onclick="alert(1)"' not in html
    assert 'test" onclick="alert(1)"' not in html


def test_golem_renderer_get_listing_roles():
    """Verify GolemRenderer.get_listing_roles returns sanitized tokens."""
    from golem.renderer import GolemRenderer

    renderer = GolemRenderer()
    node = {
        "attributes": {
            "role": 'good-badge bad/badge! other$tag" test_1',
        }
    }
    roles = renderer.get_listing_roles(node)
    assert "good-badge" in roles
    assert "test_1" in roles
    for r in roles:
        assert all(c.isalnum() or c in "-_" for c in r)


def test_listing_template_has_no_dynamic_imports():
    """Verify listing.html template does not use __import__ or eval."""
    template_path = Path("src/golem/templates/default/listing.html")
    content = template_path.read_text()
    assert "__import__" not in content
    assert "eval(" not in content


def test_copy_button_falls_back_to_source_pane():
    """Verify client JS has fallback to source pane for clipboard copy."""
    content = Path("src/golem/templates/default/skeleton.pt").read_text()
    assert 'data-tab="source"' in content  # fallback selector present


def test_role_badge_sanitizes_class_names():
    """Verify role names with special characters do not produce injected class attributes."""
    asg = {
        "name": "listing",
        "type": "block",
        "value": "x",
        "attributes": {"language": "python", "role": 'evil" class="injected'},
    }
    html = render_body(asg)
    assert 'class="injected"' not in html
    assert "badge-evil" not in html or 'badge-evil" class="injected"' not in html
