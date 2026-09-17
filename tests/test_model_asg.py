"""Tests for golem.model thin shim and typed ASG pipeline in the engine."""

from pathlib import Path
from typing import Any


def test_asg_visitor_import() -> None:
    """AsgVisitor and AsgTransformer are importable from golem.model."""
    from golem.model import AsgTransformer, AsgVisitor, Node

    assert issubclass(Node, object)
    assert issubclass(AsgVisitor, object)
    assert issubclass(AsgTransformer, AsgVisitor)


def test_asg_transformer_on_parsed_doc(tmp_path: Path) -> None:
    """AsgTransformer can walk a real parsed document and collect node names."""
    from asciidoctrine import ASGResolver, parse_to_ast
    from golem.model import AsgTransformer, Node

    adoc = tmp_path / "doc.adoc"
    adoc.write_text("= Hello\n\nA paragraph.\n\n== Section\n\nContent.\n")
    ast = parse_to_ast(adoc.read_text())
    doc = ASGResolver().resolve_to_ast(ast)

    class NameCollector(AsgTransformer):
        def __init__(self) -> None:
            self.names: list[str] = []

        def generic_visit(self, node: Node, **kwargs: Any) -> Node:
            self.names.append(node.name)
            return super().generic_visit(node, **kwargs)

    collector = NameCollector()
    collector.visit(doc)
    assert "document" in collector.names
    assert "paragraph" in collector.names
    assert "section" in collector.names


def test_engine_extracts_title_from_typed_node(tmp_path: Path) -> None:
    """BuildEngine correctly extracts title when resolve_to_ast returns a Node."""
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text("= My Doc Title\n\nSome content.\n")
    output = tmp_path / "dist"

    config = GolemConfig(content_dir=str(content), output_dir=str(output))
    engine = BuildEngine(config)
    built = engine.build_site()
    assert len(built) == 1
    html = built[0].read_text()
    assert "My Doc Title" in html


def test_engine_extracts_title_fallback_to_section(tmp_path: Path) -> None:
    """BuildEngine falls back to first section title when no document header title exists."""
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text("== Section One Title\n\nSome section content.\n")
    output = tmp_path / "dist"

    config = GolemConfig(content_dir=str(content), output_dir=str(output))
    engine = BuildEngine(config)
    built = engine.build_site()
    assert len(built) == 1
    html = built[0].read_text()
    assert "Section One Title" in html


def test_engine_extracts_attributes_from_typed_node(tmp_path: Path) -> None:
    """BuildEngine extracts body_class and page_class from typed Document attributes."""
    from golem.config import GolemConfig
    from golem.engine import BuildEngine

    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text("= Title\n:body_class: custom-body-class\n\nContent.\n")
    output = tmp_path / "dist"

    config = GolemConfig(content_dir=str(content), output_dir=str(output))
    engine = BuildEngine(config)
    built = engine.build_site()
    assert len(built) == 1
    html = built[0].read_text()
    assert "custom-body-class" in html


def test_on_asg_created_receives_typed_node(tmp_path: Path) -> None:
    """Plugins implementing on_asg_created receive a Node instance."""
    from golem.config import GolemConfig
    from golem.engine import BuildEngine
    from golem.model import Node
    from golem.plugins import hookimpl

    received_nodes: list[Node] = []

    class TestPlugin:
        @hookimpl
        def on_asg_created(self, asg: Node) -> Node:
            received_nodes.append(asg)
            return asg

    content = tmp_path / "content"
    content.mkdir()
    (content / "index.adoc").write_text("= Plugin Test\n\nContent.\n")
    output = tmp_path / "dist"

    config = GolemConfig(content_dir=str(content), output_dir=str(output))
    engine = BuildEngine(config)
    engine.pm.register(TestPlugin())
    engine.build_site()

    assert len(received_nodes) == 1
    assert isinstance(received_nodes[0], Node)
    assert received_nodes[0].name == "document"
