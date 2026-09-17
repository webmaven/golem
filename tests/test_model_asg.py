import asciidoctrine.nodes as ad_nodes
from golem.model.asg import (
    AdmonitionNode,
    DiscreteHeadingNode,
    DocumentNode,
    ImageNode,
    ListingNode,
    ListItemNode,
    ListNode,
    ParagraphNode,
    RefNode,
    SectionNode,
    TableCellNode,
    TableNode,
    TableRowNode,
    TextNode,
    asg_to_model,
    model_to_asg,
    model_to_node,
    node_from_dict,
    node_from_node,
)
from golem.model.visitor import AsgTransformer, AsgVisitor
from golem.renderer import collect_node_types, generate_toc_html, render_body


def test_typed_asg_instantiation():
    p = ParagraphNode(text="Hello world", inlines=[])
    sec = SectionNode(title="Intro", level=1, blocks=[p])
    doc = DocumentNode(title="Root Doc", blocks=[sec])
    assert doc.title == "Root Doc"
    assert len(doc.blocks) == 1
    assert isinstance(doc.blocks[0], SectionNode)


def test_asg_transformer_walk():
    class UppercaseTransformer(AsgTransformer):
        def visit_ParagraphNode(self, node: ParagraphNode) -> ParagraphNode:
            node.text = node.text.upper()
            return node

    p = ParagraphNode(text="lowercase text", inlines=[])
    doc = DocumentNode(title="Doc", blocks=[p])
    transformer = UppercaseTransformer()
    transformed_doc = transformer.transform(doc)
    assert transformed_doc.blocks[0].text == "LOWERCASE TEXT"


def test_asg_transformer_removal_and_splicing():
    class SplicingTransformer(AsgTransformer):
        def visit_ParagraphNode(self, node: ParagraphNode):
            if "remove" in node.text:
                return None  # remove node
            if "split" in node.text:
                return [
                    ParagraphNode(text="Part 1"),
                    ParagraphNode(text="Part 2"),
                ]
            return node

    p1 = ParagraphNode(text="Keep this")
    p2 = ParagraphNode(text="Please remove me")
    p3 = ParagraphNode(text="Please split me")
    doc = DocumentNode(title="Doc", blocks=[p1, p2, p3])

    transformer = SplicingTransformer()
    res = transformer.transform(doc)
    assert len(res.blocks) == 3
    assert res.blocks[0].text == "Keep this"
    assert res.blocks[1].text == "Part 1"
    assert res.blocks[2].text == "Part 2"


def test_asg_transformer_name_dispatch():
    class NameDispatchTransformer(AsgTransformer):
        def visit_section(self, node: SectionNode) -> SectionNode:
            node.title = f"Transformed: {node.title}"
            return node

    sec = SectionNode(title="Heading")
    doc = DocumentNode(title="Doc", blocks=[sec])
    res = NameDispatchTransformer().transform(doc)
    assert res.blocks[0].title == "Transformed: Heading"


def test_asg_visitor_traversal():
    visited_types = []

    class CollectingVisitor(AsgVisitor):
        def visit_ParagraphNode(self, node: ParagraphNode):
            visited_types.append("paragraph")
            self.generic_visit(node)

        def visit_SectionNode(self, node: SectionNode):
            visited_types.append("section")
            self.generic_visit(node)

        def visit_TextNode(self, node: TextNode):
            visited_types.append("text")

    p = ParagraphNode(text="hello", inlines=[TextNode(value="hello")])
    sec = SectionNode(title="Sec", blocks=[p])
    doc = DocumentNode(title="Doc", blocks=[sec])

    CollectingVisitor().visit(doc)
    assert "section" in visited_types
    assert "paragraph" in visited_types
    assert "text" in visited_types


def test_bidirectional_document_dict_conversion():
    raw_dict = {
        "name": "document",
        "type": "block",
        "title": "Sample Guide",
        "attributes": {"author": "Tester"},
        "blocks": [
            {
                "name": "section",
                "type": "block",
                "level": 1,
                "title": [{"name": "text", "type": "string", "value": "Intro"}],
                "attributes": {"id": "intro"},
                "blocks": [
                    {
                        "name": "paragraph",
                        "type": "block",
                        "inlines": [
                            {"name": "text", "type": "string", "value": "Welcome to "},
                            {
                                "name": "span",
                                "type": "inline",
                                "variant": "strong",
                                "form": "constrained",
                                "inlines": [{"name": "text", "type": "string", "value": "Golem"}],
                            },
                        ],
                    },
                    {
                        "name": "listing",
                        "type": "block",
                        "attributes": {"language": "python"},
                        "inlines": [{"name": "text", "type": "string", "value": "print('hello')"}],
                        "delimiter": "----",
                    },
                ],
            }
        ],
    }

    doc_node = node_from_dict(raw_dict)
    assert isinstance(doc_node, DocumentNode)
    assert doc_node.title == "Sample Guide"
    assert len(doc_node.blocks) == 1
    sec = doc_node.blocks[0]
    assert isinstance(sec, SectionNode)
    assert sec.title == "Intro"
    assert sec.id == "intro"
    assert len(sec.blocks) == 2
    assert isinstance(sec.blocks[0], ParagraphNode)
    assert isinstance(sec.blocks[1], ListingNode)
    assert sec.blocks[1].language == "python"

    # Serialize back to dict
    serialized = doc_node.to_dict()
    assert serialized["name"] == "document"
    assert serialized["title"] == "Sample Guide"
    assert serialized["blocks"][0]["name"] == "section"
    assert serialized["blocks"][0]["attributes"]["id"] == "intro"
    assert serialized["blocks"][0]["blocks"][1]["attributes"]["language"] == "python"


def test_bidirectional_asciidoctrine_node_conversion():
    p_ast = ad_nodes.Paragraph(inlines=[ad_nodes.Text("Some text in paragraph")])
    sec_ast = ad_nodes.Section(level=2, title=ad_nodes.Title([ad_nodes.Text("Details")]), blocks=[p_ast])
    doc_ast = ad_nodes.Document(blocks=[sec_ast])
    doc_ast.attributes["doctitle"] = "AST Document"

    # AST -> Model
    doc_model = node_from_node(doc_ast)
    assert isinstance(doc_model, DocumentNode)
    assert doc_model.title == "AST Document"
    assert len(doc_model.blocks) == 1
    assert isinstance(doc_model.blocks[0], SectionNode)
    assert doc_model.blocks[0].level == 2
    assert doc_model.blocks[0].title == "Details"
    assert isinstance(doc_model.blocks[0].blocks[0], ParagraphNode)
    assert doc_model.blocks[0].blocks[0].text == "Some text in paragraph"

    # Model -> AST
    roundtrip_ast = doc_model.to_node()
    assert isinstance(roundtrip_ast, ad_nodes.Document)
    assert len(roundtrip_ast.blocks) == 1
    assert isinstance(roundtrip_ast.blocks[0], ad_nodes.Section)
    assert roundtrip_ast.blocks[0].level == 2
    assert isinstance(roundtrip_ast.blocks[0].blocks[0], ad_nodes.Paragraph)


def test_table_and_admonition_and_heading_models():
    cell1 = TableCellNode(text="Cell A")
    cell2 = TableCellNode(text="Cell B")
    row = TableRowNode(cells=[cell1, cell2])
    table = TableNode(rows=[row], columns=[{"width": 50}, {"width": 50}])
    admon = AdmonitionNode(variant="WARNING", blocks=[ParagraphNode(text="Beware!")])
    heading = DiscreteHeadingNode(title="Floating", level=3)

    doc = DocumentNode(title="Misc", blocks=[table, admon, heading])

    # Test conversion to dict
    d = doc.to_dict()
    assert d["blocks"][0]["name"] == "table"
    assert len(d["blocks"][0]["rows"]) == 1
    assert len(d["blocks"][0]["rows"][0]["cells"]) == 2
    assert d["blocks"][1]["name"] == "admonition"
    assert d["blocks"][1]["variant"] == "WARNING"
    assert d["blocks"][2]["name"] == "floatingTitle"
    assert d["blocks"][2]["level"] == 3

    # Test round-trip from dict
    restored = node_from_dict(d)
    assert isinstance(restored.blocks[0], TableNode)
    assert isinstance(restored.blocks[1], AdmonitionNode)
    assert isinstance(restored.blocks[2], DiscreteHeadingNode)

    # Test conversion to AST nodes
    table_ast = table.to_node()
    assert isinstance(table_ast, ad_nodes.Table)
    admon_ast = admon.to_node()
    assert isinstance(admon_ast, ad_nodes.Admonition)
    heading_ast = heading.to_node()
    assert isinstance(heading_ast, ad_nodes.FloatingTitle)


def test_list_and_image_and_ref_models():
    item1 = ListItemNode(principal=[TextNode(value="First item")])
    item2 = ListItemNode(principal=[TextNode(value="Second item")])
    lst = ListNode(variant="ordered", marker=".", items=[item1, item2])
    img = ImageNode(target="diagram.png", alt="A diagram")
    ref = RefNode(variant="link", target="https://example.com", inlines=[TextNode(value="Example")])
    p = ParagraphNode(inlines=[ref])

    doc = DocumentNode(title="Lists and Images", blocks=[lst, img, p])
    d = doc.to_dict()
    assert d["blocks"][0]["name"] == "list"
    assert d["blocks"][1]["name"] == "image"
    assert d["blocks"][2]["inlines"][0]["name"] == "ref"

    restored = node_from_dict(d)
    assert isinstance(restored.blocks[0], ListNode)
    assert isinstance(restored.blocks[1], ImageNode)
    assert isinstance(restored.blocks[2].inlines[0], RefNode)

    # AST conversion
    assert isinstance(lst.to_node(), ad_nodes.List)
    assert isinstance(img.to_node(), ad_nodes.Image)
    assert isinstance(ref.to_node(), ad_nodes.Ref)


def test_universal_adapters():
    p = ParagraphNode(text="Adapters test")
    doc = DocumentNode(title="Universal", blocks=[p])

    # asg_to_model on BaseNode
    assert asg_to_model(doc) is doc

    # asg_to_model on dict
    doc_dict = doc.to_dict()
    from_dict_doc = asg_to_model(doc_dict)
    assert isinstance(from_dict_doc, DocumentNode)

    # asg_to_model on AST Node
    doc_ast = doc.to_node()
    from_node_doc = asg_to_model(doc_ast)
    assert isinstance(from_node_doc, DocumentNode)

    # model_to_asg & model_to_node
    assert isinstance(model_to_asg(doc), dict)
    assert isinstance(model_to_node(doc), ad_nodes.Document)


def test_renderer_integration_with_typed_models():
    p = ParagraphNode(text="Paragraph rendered directly from DocumentNode")
    sec = SectionNode(title="Getting Started", level=1, blocks=[p])
    doc = DocumentNode(title="Documentation", blocks=[sec])

    # render_body directly accepts DocumentNode
    html = render_body(doc)
    assert "Getting Started" in html
    assert "Paragraph rendered directly from DocumentNode" in html

    # generate_toc_html directly accepts DocumentNode
    toc = generate_toc_html(doc)
    assert '<nav class="toc">' in toc
    assert 'href="#getting-started"' in toc
    assert "Getting Started" in toc

    # collect_node_types directly accepts DocumentNode
    node_types = collect_node_types(doc)
    assert "document" in node_types
    assert "section" in node_types
    assert "paragraph" in node_types
