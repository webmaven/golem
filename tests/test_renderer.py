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
