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
    # The default resolver transforms attributes and filters comments
    from asciidoctrine.resolver import ASGResolver
    resolver = asciidoctrine.resolver.ASGResolver(ast)
    asg = resolver.resolve(ast)
    
    html = render_body(asg)
    assert "This is a premier paragraph with <strong>bold</strong> text" in html
    assert "<pre><code class=\"language-python\">import sys\nprint(sys.version)\n</code></pre>" in html
