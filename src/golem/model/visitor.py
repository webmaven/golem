"""Visitor and Transformer patterns for ASG domain models and AsciiDoc ASTs.

Provides `AsgVisitor` and `AsgTransformer` with dynamic method dispatch (`visit_<NodeType>`),
supporting AST traversal, selective mutation, node removal (returning `None`),
and multi-node splicing (returning a `list`).
"""

from __future__ import annotations

from typing import Any


class AsgVisitor:
    """Base visitor for traversing ASG domain models, asciidoctrine ASTs, and ASG dicts."""

    def visit(self, node: Any, **kwargs: Any) -> Any:
        """Dispatch visiting to a typed method or generic_visit.

        Dispatch resolution order:
        1. `visit_<ClassName>` (e.g. `visit_ParagraphNode`)
        2. `visit_<ClassName>Node` if class does not end in 'Node' (e.g. `visit_ParagraphNode` for `Paragraph`)
        3. `visit_<node_name>` (e.g. `visit_paragraph` for `node.name == "paragraph"`)
        4. `visit_<PascalCaseName>Node` (e.g. `visit_ParagraphNode` for `name="paragraph"`)
        5. `self.generic_visit(node, **kwargs)`
        """
        if node is None:
            return None

        class_name = node.__class__.__name__

        # 1. Exact class name (e.g. visit_ParagraphNode)
        visitor = getattr(self, f"visit_{class_name}", None)
        if visitor is not None:
            return visitor(node, **kwargs)

        # 2. Append 'Node' if not present (e.g. asciidoctrine.nodes.Paragraph -> visit_ParagraphNode)
        if not class_name.endswith("Node"):
            visitor = getattr(self, f"visit_{class_name}Node", None)
            if visitor is not None:
                return visitor(node, **kwargs)

        # 3. Name-based dispatch (e.g. visit_paragraph)
        node_name = getattr(node, "name", None)
        if node_name is None and isinstance(node, dict):
            node_name = node.get("name")

        if node_name and isinstance(node_name, str):
            clean_name = node_name.lower().replace("-", "_")
            visitor = getattr(self, f"visit_{clean_name}", None)
            if visitor is not None:
                return visitor(node, **kwargs)

            # 4. PascalCase node name with Node suffix (e.g. name="section" -> visit_SectionNode)
            pascal = "".join(part.capitalize() for part in clean_name.split("_"))
            visitor = getattr(self, f"visit_{pascal}Node", None)
            if visitor is not None:
                return visitor(node, **kwargs)

        return self.generic_visit(node, **kwargs)

    def generic_visit(self, node: Any, **kwargs: Any) -> Any:
        """Traverse child collections of the current node."""
        if hasattr(node, "get_child_collections"):
            for collection in node.get_child_collections().values():
                for child in collection:
                    self.visit(child, **kwargs)
        elif isinstance(node, dict):
            for key in ("blocks", "inlines", "children", "items", "rows", "cells", "principal", "title_inlines"):
                if key in node and isinstance(node[key], list):
                    for child in node[key]:
                        self.visit(child, **kwargs)
        elif isinstance(node, list):
            for item in node:
                self.visit(item, **kwargs)
        return None


class AsgTransformer(AsgVisitor):
    """Base transformer for rewriting ASG domain models, asciidoctrine ASTs, and ASG dicts."""

    def transform(self, doc: Any, **kwargs: Any) -> Any:
        """Transform an ASG root document or sub-tree, returning the modified root."""
        return self.visit(doc, **kwargs)

    def generic_visit(self, node: Any, **kwargs: Any) -> Any:
        """Recursively walk and rewrite child collections in-place."""
        if node is None:
            return None

        if hasattr(node, "get_child_collections"):
            collections = node.get_child_collections()
            for attr_name, items in collections.items():
                new_items = self._transform_list(items, **kwargs)
                setattr(node, attr_name, new_items)

            if hasattr(node, "header") and node.header is not None:
                node.header = self.visit(node.header, **kwargs)
            if hasattr(node, "docinfo") and node.docinfo is not None:
                node.docinfo = self.visit(node.docinfo, **kwargs)
            return node

        if isinstance(node, dict):
            for key in ("blocks", "inlines", "children", "items", "rows", "cells", "principal", "title_inlines"):
                if key in node and isinstance(node[key], list):
                    node[key] = self._transform_list(node[key], **kwargs)
            if "header" in node and isinstance(node["header"], dict):
                node["header"] = self.visit(node["header"], **kwargs)
            if "docinfo" in node and isinstance(node["docinfo"], dict):
                node["docinfo"] = self.visit(node["docinfo"], **kwargs)
            return node

        if isinstance(node, list):
            return self._transform_list(node, **kwargs)

        return node

    def _transform_list(self, items: list[Any], **kwargs: Any) -> list[Any]:
        """Apply visit to a list of items, supporting removal (None) and splicing (list)."""
        new_items: list[Any] = []
        for item in items:
            res = self.visit(item, **kwargs)
            if res is None:
                continue
            elif isinstance(res, list):
                new_items.extend(res)
            else:
                new_items.append(res)
        return new_items
