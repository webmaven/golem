import pytest
import asciidoctrine
from golem.renderer import render_body

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
    from asciidoctrine.resolver import ASGResolver
    resolver = ASGResolver(ast)
    asg = resolver.resolve(ast)
    html = render_body(asg)
    assert "This is a premier paragraph with <strong>bold</strong> text" in html
    assert "<pre><code class=\"language-python\">import sys\nprint(sys.version)\n</code></pre>" in html


def test_html_listing_escaping():
    adoc_source = """
[source,python]
----
html = compiler.compile_page("Developer Guide", "<p>Content goes here</p>", "")
----
"""
    ast = asciidoctrine.parse_to_ast(adoc_source)
    from asciidoctrine.resolver import ASGResolver
    resolver = ASGResolver(ast)
    asg = resolver.resolve(ast)
    
    html_output = render_body(asg)
    # The literal '<p>' should be safely escaped in HTML rendering to '&lt;p&gt;'
    assert "&lt;p&gt;Content goes here&lt;/p&gt;" in html_output
    assert "<p>Content goes here</p>" not in html_output


def test_render_lists_and_checkboxes():
    from golem.renderer import HtmlRenderer
    from asciidoctrine.nodes import List, ListItem, Text
    
    # Test unordered checkbox list
    item1 = ListItem(marker="*", principal=[Text("Task one")], checked=True)
    item2 = ListItem(marker="*", principal=[Text("Task two")], checked=False)
    item3 = ListItem(marker="*", principal=[Text("Standard item")], checked=None)
    
    ulist = List(variant="unordered", marker="*", items=[item1, item2, item3])
    renderer = HtmlRenderer()
    html = renderer.render(ulist)
    
    assert "<ul>" in html
    assert "</ul>" in html
    assert '<li><input type="checkbox" checked disabled /> Task one</li>' in html
    assert '<li><input type="checkbox" disabled /> Task two</li>' in html
    assert '<li>Standard item</li>' in html

    # Test ordered list
    oitem1 = ListItem(marker="1.", principal=[Text("First item")])
    olist = List(variant="ordered", marker="1.", items=[oitem1])
    html_ordered = renderer.render(olist)
    assert "<ol>" in html_ordered
    assert "</ol>" in html_ordered
    assert "<li>First item</li>" in html_ordered

