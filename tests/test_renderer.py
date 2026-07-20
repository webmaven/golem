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


def test_render_description_lists_and_admonitions():
    from golem.renderer import HtmlRenderer
    from asciidoctrine.nodes import DescriptionList, DescriptionListItem, DescriptionListTerm, Paragraph, Text, Admonition
    
    term = DescriptionListTerm(inlines=[Text("Term 1")])
    body = Paragraph(inlines=[Text("Definition 1")])
    item = DescriptionListItem(terms=[term], blocks=[body])
    dlist = DescriptionList(items=[item])
    
    admonition = Admonition(variant="note", blocks=[Paragraph(inlines=[Text("This is a note")])])
    
    renderer = HtmlRenderer()
    
    # Test description list rendering
    html_dlist = renderer.render(dlist)
    assert "<dl>" in html_dlist
    assert "<dt>Term 1</dt>" in html_dlist
    assert "<dd>" in html_dlist
    assert "Definition 1" in html_dlist
    assert "</dl>" in html_dlist
    
    # Test admonition rendering
    html_admonition = renderer.render(admonition)
    assert '<div class="admonition note">' in html_admonition
    assert '<div class="admonition-title">NOTE</div>' in html_admonition
    assert 'This is a note' in html_admonition


def test_render_images_and_tables():
    from golem.renderer import HtmlRenderer
    from asciidoctrine.nodes import Image, Table, TableRow, TableCell, Paragraph, Text
    
    # Test Image
    img = Image(target="images/logo.png", alt="Logo alt text")
    
    # Test Table
    cell1 = TableCell(blocks=[Paragraph(inlines=[Text("Cell A")])])
    cell1.colspan = 2
    cell2 = TableCell(blocks=[Paragraph(inlines=[Text("Cell B")])])
    cell2.align = "right"
    
    row = TableRow(cells=[cell1, cell2])
    table = Table(rows=[row])
    
    renderer = HtmlRenderer()
    
    # Test Image
    html_img = renderer.render(img)
    assert '<img src="images/logo.png" alt="Logo alt text" />' in html_img
    
    # Test Table
    html_tbl = renderer.render(table)
    assert "<table>" in html_tbl
    assert "<tr>" in html_tbl
    assert '<td colspan="2">' in html_tbl
    assert '<td align="right">' in html_tbl
    assert "Cell A" in html_tbl
    assert "</table>" in html_tbl


def test_generate_toc_html():
    from golem.renderer import generate_toc_html
    from asciidoctrine.nodes import Document, Section, Text
    
    sec1 = Section(level=1, title=[Text("Introduction")])
    sec2 = Section(level=2, title=[Text("Details")])
    doc = Document(blocks=[sec1, sec2])
    
    toc_html = generate_toc_html(doc)
    assert '<ul class="toc-list">' in toc_html
    assert '<a href="#introduction">Introduction</a>' in toc_html
    assert '<ul class="toc-level-2">' in toc_html
    assert '<a href="#details">Details</a>' in toc_html

