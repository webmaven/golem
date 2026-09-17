"""Typed ASG domain models mirroring AsciiDoc AST and ASG nodes.

Provides type-safe dataclass node wrappers for all structural elements of an AsciiDoc document,
supporting bidirectional conversion to and from raw ASG dictionaries and `asciidoctrine.nodes.Node` AST objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Optional, Union
import asciidoctrine.nodes as ad_nodes


def _extract_plain_text(node: Any) -> str:
    """Recursively extract plain string representations from nested inlines or AST nodes."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_extract_plain_text(item) for item in node)
    if isinstance(node, dict):
        if node.get("name") == "text":
            return str(node.get("value", ""))
        if "value" in node and isinstance(node["value"], (str, int, float)):
            return str(node["value"])
        if "text" in node and isinstance(node["text"], (str, int, float)):
            return str(node["text"])
        res = []
        for key in ("inlines", "children", "title"):
            if key in node and isinstance(node[key], (list, dict, str)):
                res.append(_extract_plain_text(node[key]))
        return "".join(res)
    if hasattr(node, "value") and node.value is not None:
        return str(node.value)
    if hasattr(node, "text") and node.text is not None:
        return str(node.text)
    res = []
    if hasattr(node, "inlines") and node.inlines:
        res.append(_extract_plain_text(node.inlines))
    elif hasattr(node, "title") and node.title:
        res.append(_extract_plain_text(node.title))
    elif hasattr(node, "get_child_collections"):
        for collection in node.get_child_collections().values():
            for child in collection:
                res.append(_extract_plain_text(child))
    return "".join(res)


@dataclass
class BaseNode:
    """Base class for all typed ASG domain model nodes."""

    name: str = "unknown"
    type: str = "block"
    attributes: dict[str, Any] = field(default_factory=dict)
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        """Return a mapping of collection names to child node lists."""
        return {}

    def walk(self) -> Iterator[BaseNode]:
        """Recursively walk the node hierarchy, yielding each node."""
        yield self
        for collection in self.get_child_collections().values():
            for child in collection:
                if isinstance(child, BaseNode):
                    yield from child.walk()

    def to_dict(self) -> dict[str, Any]:
        """Serialize this node to an ASG-compatible dictionary."""
        data: dict[str, Any] = {"name": self.name, "type": self.type}
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.location is not None:
            data["location"] = self.location
        for key, collection in self.get_child_collections().items():
            data[key] = [c.to_dict() if hasattr(c, "to_dict") else c for c in collection]
        return data

    def to_node(self) -> ad_nodes.Node:
        """Convert this typed node to an asciidoctrine AST Node instance."""
        node = ad_nodes.Node()
        node.name = self.name
        node.type = self.type
        node.attributes = dict(self.attributes)
        node.location = self.location
        return node

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseNode:
        """Construct a typed node from an ASG dictionary."""
        return node_from_dict(data)

    @classmethod
    def from_node(cls, node: ad_nodes.Node) -> BaseNode:
        """Construct a typed node from an asciidoctrine AST Node."""
        return node_from_node(node)


@dataclass
class BlockNode(BaseNode):
    """Base class for block-level structural nodes."""

    type: str = "block"
    blocks: list[BaseNode] = field(default_factory=list)

    def get_child_collections(self) -> dict[str, list[Any]]:
        collections: dict[str, list[Any]] = {}
        if self.blocks:
            collections["blocks"] = self.blocks
        return collections

    def append(self, child: BaseNode) -> None:
        """Append a child block to this node."""
        self.blocks.append(child)


@dataclass
class InlineNode(BaseNode):
    """Base class for inline content and text formatting nodes."""

    type: str = "inline"
    inlines: list[BaseNode] = field(default_factory=list)

    def get_child_collections(self) -> dict[str, list[Any]]:
        collections: dict[str, list[Any]] = {}
        if self.inlines:
            collections["inlines"] = self.inlines
        return collections

    def append(self, child: BaseNode) -> None:
        """Append a child inline node."""
        self.inlines.append(child)


@dataclass
class TextNode(InlineNode):
    """Leaf node representing a segment of plain text."""

    name: str = "text"
    type: str = "string"
    value: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "type": self.type, "value": self.value}
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Text:
        node = ad_nodes.Text(value=self.value)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class TitleNode(InlineNode):
    """Inline container representing a section or document title."""

    name: str = "title"
    type: str = "inline"
    inlines: list[BaseNode] = field(default_factory=list)

    @property
    def text(self) -> str:
        return _extract_plain_text(self.inlines)

    def to_node(self) -> ad_nodes.Title:
        node = ad_nodes.Title(inlines=[i.to_node() for i in self.inlines])
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class AuthorNode(InlineNode):
    """Header author metadata node."""

    name: str = "author"
    type: str = "inline"
    inlines: list[BaseNode] = field(default_factory=list)

    @property
    def fullname(self) -> str:
        return _extract_plain_text(self.inlines)

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["fullname"] = self.fullname
        return data

    def to_node(self) -> ad_nodes.Author:
        node = ad_nodes.Author(inlines=[i.to_node() for i in self.inlines])
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class RevisionNode(BlockNode):
    """Header revision metadata node."""

    name: str = "revision"
    type: str = "block"
    value: str = ""
    inlines: list[BaseNode] = field(default_factory=list)

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"inlines": self.inlines} if self.inlines else {}

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["value"] = self.value or _extract_plain_text(self.inlines)
        return data

    def to_node(self) -> ad_nodes.Revision:
        node = ad_nodes.Revision(inlines=[i.to_node() for i in self.inlines])
        node.value = self.value
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class DocinfoNode(BaseNode):
    """Header and footer injected document metadata."""

    name: str = "docinfo"
    type: str = "metadata"
    head_content: str = ""
    footer_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["head_content"] = self.head_content
        data["footer_content"] = self.footer_content
        return data

    def to_node(self) -> ad_nodes.Docinfo:
        node = ad_nodes.Docinfo(head_content=self.head_content, footer_content=self.footer_content)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class HeaderNode(BaseNode):
    """Document header container node."""

    name: str = "header"
    type: str = "block"
    title: Optional[TitleNode] = None
    authors: list[AuthorNode] = field(default_factory=list)
    revision: Optional[RevisionNode] = None
    docinfo: Optional[DocinfoNode] = None

    @property
    def title_text(self) -> str:
        return self.title.text if self.title else ""

    def to_dict(self) -> dict[str, Any]:
        header_data: dict[str, Any] = {}
        if self.title:
            header_data["title"] = [n.to_dict() for n in self.title.inlines]
        if self.authors:
            header_data["authors"] = [{"fullname": a.fullname} for a in self.authors]
        if self.revision:
            header_data["revision"] = self.revision.to_dict()
        if self.docinfo:
            header_data["docinfo"] = self.docinfo.to_dict()
        if self.attributes:
            header_data["attributes"] = dict(self.attributes)
        return header_data

    def to_node(self) -> ad_nodes.Header:
        title_ast = self.title.to_node() if self.title else None
        authors_ast = [a.to_node() for a in self.authors]
        rev_ast = self.revision.to_node() if self.revision else None
        docinfo_ast = self.docinfo.to_node() if self.docinfo else None
        node = ad_nodes.Header(
            title=title_ast,
            authors=authors_ast,
            revision=rev_ast,
            attributes=dict(self.attributes),
            docinfo=docinfo_ast,
        )
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class DocumentNode(BlockNode):
    """Root node of an AsciiDoc document AST/ASG structure."""

    name: str = "document"
    type: str = "block"
    title: str = ""
    blocks: list[BaseNode] = field(default_factory=list)
    header: Optional[HeaderNode] = None
    docinfo: Optional[DocinfoNode] = None
    footnotes: list[dict[str, Any]] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    base_dir: Optional[str] = None
    safe_mode: int = 0
    location: Optional[list[dict[str, int]]] = None

    def __post_init__(self) -> None:
        if not self.title:
            if self.header and self.header.title_text:
                self.title = self.header.title_text
            elif "doctitle" in self.attributes:
                self.title = str(self.attributes["doctitle"])

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "blocks": [b.to_dict() for b in self.blocks],
        }
        if self.title:
            data["title"] = self.title
        if self.header:
            data["header"] = self.header.to_dict()
        if self.docinfo:
            data["docinfo"] = self.docinfo.to_dict()
        if self.footnotes:
            data["footnotes"] = list(self.footnotes)
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Document:
        doc = ad_nodes.Document(
            blocks=[b.to_node() for b in self.blocks],
            base_dir=self.base_dir,
            safe_mode=self.safe_mode,
        )
        doc.attributes = dict(self.attributes)
        if self.header:
            doc.header = self.header.to_node()
        elif self.title:
            doc.header = ad_nodes.Header(
                title=ad_nodes.Title([ad_nodes.Text(self.title)]),
                attributes=dict(self.attributes),
            )
            doc.attributes.setdefault("doctitle", self.title)
        if self.docinfo:
            doc.docinfo = self.docinfo.to_node()
        if self.footnotes:
            doc.footnotes = list(self.footnotes)
        if self.location is not None:
            doc.location = self.location
        return doc


@dataclass
class SectionNode(BlockNode):
    """Structural section container node."""

    name: str = "section"
    type: str = "block"
    title: str = ""
    level: int = 1
    blocks: list[BaseNode] = field(default_factory=list)
    title_inlines: list[BaseNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    location: Optional[list[dict[str, int]]] = None

    def __post_init__(self) -> None:
        if self.title and not self.title_inlines:
            self.title_inlines = [TextNode(value=self.title)]
        elif not self.title and self.title_inlines:
            self.title = _extract_plain_text(self.title_inlines)

    @property
    def id(self) -> Optional[str]:
        return self.attributes.get("id")

    @id.setter
    def id(self, value: Optional[str]) -> None:
        if value is None:
            self.attributes.pop("id", None)
        else:
            self.attributes["id"] = value

    def _sync_title(self) -> None:
        if self.title_inlines:
            current_inlines_text = _extract_plain_text(self.title_inlines)
            if self.title != current_inlines_text:
                if len(self.title_inlines) == 1 and isinstance(self.title_inlines[0], TextNode):
                    self.title_inlines[0].value = self.title
                else:
                    self.title_inlines = [TextNode(value=self.title)]
        elif self.title:
            self.title_inlines = [TextNode(value=self.title)]

    def to_dict(self) -> dict[str, Any]:
        self._sync_title()
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "level": self.level,
            "title": [i.to_dict() for i in self.title_inlines]
            if self.title_inlines
            else [{"name": "text", "type": "string", "value": self.title}],
            "blocks": [b.to_dict() for b in self.blocks],
        }
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Section:
        self._sync_title()
        sec = ad_nodes.Section(
            level=self.level,
            title=ad_nodes.Title([i.to_node() for i in self.title_inlines]),
            blocks=[b.to_node() for b in self.blocks],
        )
        sec.attributes = dict(self.attributes)
        if self.location is not None:
            sec.location = self.location
        return sec


@dataclass
class ParagraphNode(BlockNode):
    """Block-level paragraph of text with nested inlines."""

    name: str = "paragraph"
    type: str = "block"
    text: str = ""
    inlines: list[BaseNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def __post_init__(self) -> None:
        if self.text and not self.inlines:
            self.inlines = [TextNode(value=self.text)]
        elif not self.text and self.inlines:
            self.text = _extract_plain_text(self.inlines)

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"inlines": self.inlines}

    def _sync_text(self) -> None:
        if self.inlines:
            current_inlines_text = _extract_plain_text(self.inlines)
            if self.text != current_inlines_text:
                if len(self.inlines) == 1 and isinstance(self.inlines[0], TextNode):
                    self.inlines[0].value = self.text
                else:
                    self.inlines = [TextNode(value=self.text)]
        elif self.text:
            self.inlines = [TextNode(value=self.text)]

    def to_dict(self) -> dict[str, Any]:
        self._sync_text()
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "inlines": [i.to_dict() for i in self.inlines],
        }
        if self.text:
            data["text"] = self.text
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.title:
            data["title"] = self.title
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Paragraph:
        self._sync_text()
        p = ad_nodes.Paragraph(inlines=[i.to_node() for i in self.inlines])
        p.attributes = dict(self.attributes)
        if self.title:
            p.title = ad_nodes.Title([ad_nodes.Text(self.title)])
        if self.location is not None:
            p.location = self.location
        return p


@dataclass
class ListingNode(BlockNode):
    """Verbatim source code or preformatted listing block."""

    name: str = "listing"
    type: str = "block"
    code: str = ""
    language: str = ""
    inlines: list[BaseNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    delimiter: str = "----"
    title: Optional[str] = None
    form: str = "delimited"
    location: Optional[list[dict[str, int]]] = None

    def __post_init__(self) -> None:
        if self.code and not self.inlines:
            self.inlines = [TextNode(value=self.code)]
        elif not self.code and self.inlines:
            self.code = _extract_plain_text(self.inlines)

        if self.language and "language" not in self.attributes:
            self.attributes["language"] = self.language
        elif not self.language and "language" in self.attributes:
            self.language = str(self.attributes["language"])

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"inlines": self.inlines}

    def _sync_code(self) -> None:
        if self.inlines:
            current_code = _extract_plain_text(self.inlines)
            if self.code != current_code:
                if len(self.inlines) == 1 and isinstance(self.inlines[0], TextNode):
                    self.inlines[0].value = self.code
                else:
                    self.inlines = [TextNode(value=self.code)]
        elif self.code:
            self.inlines = [TextNode(value=self.code)]
        if self.language:
            self.attributes["language"] = self.language

    def to_dict(self) -> dict[str, Any]:
        self._sync_code()
        attrs = dict(self.attributes)
        if self.language:
            attrs["language"] = self.language
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "form": self.form,
            "delimiter": self.delimiter,
            "inlines": [i.to_dict() for i in self.inlines],
        }
        if self.code:
            data["value"] = self.code
        if attrs:
            data["attributes"] = attrs
        if self.title:
            data["title"] = self.title
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Listing:
        self._sync_code()
        attrs = dict(self.attributes)
        if self.language:
            attrs["language"] = self.language
        node = ad_nodes.Listing(
            inlines=[i.to_node() for i in self.inlines],
            attributes=attrs,
            delimiter=self.delimiter,
        )
        if self.title:
            node.title = ad_nodes.Title([ad_nodes.Text(self.title)])
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class TableCellNode(BlockNode):
    """Single cell within a table row."""

    name: str = "cell"
    type: str = "block"
    blocks: list[BaseNode] = field(default_factory=list)
    text: str = ""
    inlines: list[BaseNode] = field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1
    align: Optional[str] = None
    valign: Optional[str] = None
    style: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        collections: dict[str, list[Any]] = {}
        if self.blocks:
            collections["blocks"] = self.blocks
        if self.inlines:
            collections["inlines"] = self.inlines
        return collections

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "colspan": self.colspan,
            "rowspan": self.rowspan,
        }
        if self.blocks:
            data["blocks"] = [b.to_dict() for b in self.blocks]
        if self.inlines:
            data["inlines"] = [i.to_dict() for i in self.inlines]
        elif self.text:
            data["inlines"] = [{"name": "text", "type": "string", "value": self.text}]
        if self.align:
            data["align"] = self.align
        if self.valign:
            data["valign"] = self.valign
        if self.style:
            data["style"] = self.style
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.TableCell:
        node = ad_nodes.TableCell(blocks=[b.to_node() for b in self.blocks])
        node.colspan = self.colspan
        node.rowspan = self.rowspan
        node.align = self.align
        node.valign = self.valign
        node.style = self.style
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class TableRowNode(BaseNode):
    """Single row within a table."""

    name: str = "row"
    type: str = "block"
    cells: list[TableCellNode] = field(default_factory=list)
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"cells": self.cells}

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "cells": [c.to_dict() for c in self.cells],
        }
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.TableRow:
        node = ad_nodes.TableRow(cells=[c.to_node() for c in self.cells])
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class TableNode(BlockNode):
    """Structured table block."""

    name: str = "table"
    type: str = "block"
    rows: list[TableRowNode] = field(default_factory=list)
    columns: Optional[list[dict[str, Any]]] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"rows": self.rows}

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "rows": [r.to_dict() for r in self.rows],
        }
        if self.columns is not None:
            data["columns"] = self.columns
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.title:
            data["title"] = self.title
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Table:
        node = ad_nodes.Table(
            rows=[r.to_node() for r in self.rows],
            columns=self.columns,
        )
        node.attributes = dict(self.attributes)
        if self.title:
            node.title = ad_nodes.Title([ad_nodes.Text(self.title)])
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class AdmonitionNode(BlockNode):
    """Admonition block (NOTE, TIP, WARNING, CAUTION, IMPORTANT)."""

    name: str = "admonition"
    type: str = "block"
    variant: str = "NOTE"
    blocks: list[BaseNode] = field(default_factory=list)
    delimiter: Optional[str] = "===="
    form: str = "delimited"
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "variant": self.variant,
            "form": self.form,
            "delimiter": self.delimiter,
            "blocks": [b.to_dict() for b in self.blocks],
        }
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.title:
            data["title"] = self.title
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Admonition:
        node = ad_nodes.Admonition(
            variant=self.variant,
            blocks=[b.to_node() for b in self.blocks],
            delimiter=self.delimiter,
        )
        node.attributes = dict(self.attributes)
        if self.title:
            node.title = ad_nodes.Title([ad_nodes.Text(self.title)])
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class DiscreteHeadingNode(BlockNode):
    """Discrete or floating heading block that does not create a new section container."""

    name: str = "floatingTitle"
    type: str = "block"
    title: str = ""
    level: int = 1
    title_inlines: list[BaseNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    location: Optional[list[dict[str, int]]] = None

    def __post_init__(self) -> None:
        if self.title and not self.title_inlines:
            self.title_inlines = [TextNode(value=self.title)]
        elif not self.title and self.title_inlines:
            self.title = _extract_plain_text(self.title_inlines)

    def _sync_title(self) -> None:
        if self.title_inlines:
            current_inlines_text = _extract_plain_text(self.title_inlines)
            if self.title != current_inlines_text:
                if len(self.title_inlines) == 1 and isinstance(self.title_inlines[0], TextNode):
                    self.title_inlines[0].value = self.title
                else:
                    self.title_inlines = [TextNode(value=self.title)]
        elif self.title:
            self.title_inlines = [TextNode(value=self.title)]

    def to_dict(self) -> dict[str, Any]:
        self._sync_title()
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "level": self.level,
            "title": [i.to_dict() for i in self.title_inlines]
            if self.title_inlines
            else [{"name": "text", "type": "string", "value": self.title}],
        }
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Node:
        self._sync_title()
        title_ast = ad_nodes.Title([i.to_node() for i in self.title_inlines])
        ft_cls = getattr(ad_nodes, "FloatingTitle", None)
        if ft_cls is not None:
            node = ft_cls(level=self.level, title=title_ast)
        else:
            node = ad_nodes.Node()
            node.name = "floatingTitle"
            node.type = "block"
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


# Alias for compatibility with AsciiDoc / asciidoctrine terminology
FloatingTitleNode = DiscreteHeadingNode


@dataclass
class SpanNode(InlineNode):
    """Inline stylized text span (bold, italic, monospace, mark, sub, sup)."""

    name: str = "span"
    type: str = "inline"
    variant: str = "strong"
    form: str = "constrained"
    inlines: list[BaseNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    location: Optional[list[dict[str, int]]] = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["variant"] = self.variant
        data["form"] = self.form
        return data

    def to_node(self) -> ad_nodes.Span:
        node = ad_nodes.Span(
            variant=self.variant,
            inlines=[i.to_node() for i in self.inlines],
            form=self.form,
        )
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class RefNode(InlineNode):
    """Inline hyperlink, cross-reference, anchor, or footnote reference."""

    name: str = "ref"
    type: str = "inline"
    variant: str = "link"
    target: str = ""
    inlines: list[BaseNode] = field(default_factory=list)
    resolved_strategy: Optional[str] = None
    resolved_file_target: Optional[str] = None
    resolved_anchor_target: Optional[str] = None
    index: Optional[int] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    location: Optional[list[dict[str, int]]] = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["variant"] = self.variant
        data["target"] = self.target
        if self.resolved_strategy is not None:
            data["resolved_strategy"] = self.resolved_strategy
        if self.resolved_file_target is not None:
            data["resolved_file_target"] = self.resolved_file_target
        if self.resolved_anchor_target is not None:
            data["resolved_anchor_target"] = self.resolved_anchor_target
        if self.index is not None:
            data["index"] = self.index
        return data

    def to_node(self) -> ad_nodes.Ref:
        node = ad_nodes.Ref(
            variant=self.variant,
            target=self.target,
            inlines=[i.to_node() for i in self.inlines],
        )
        node.attributes = dict(self.attributes)
        node.resolved_strategy = self.resolved_strategy
        node.resolved_file_target = self.resolved_file_target
        node.resolved_anchor_target = self.resolved_anchor_target
        node.index = self.index
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class ListItemNode(BlockNode):
    """Item within an ordered or unordered list."""

    name: str = "listItem"
    type: str = "block"
    marker: str = "*"
    principal: list[BaseNode] = field(default_factory=list)
    blocks: list[BaseNode] = field(default_factory=list)
    checked: Optional[bool] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        collections: dict[str, list[Any]] = {}
        if self.principal:
            collections["principal"] = self.principal
        if self.blocks:
            collections["blocks"] = self.blocks
        return collections

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["marker"] = self.marker
        if self.checked is not None:
            data["checked"] = self.checked
        return data

    def to_node(self) -> ad_nodes.ListItem:
        node = ad_nodes.ListItem(
            marker=self.marker,
            principal=[p.to_node() for p in self.principal],
            blocks=[b.to_node() for b in self.blocks],
            checked=self.checked,
        )
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class ListNode(BlockNode):
    """List block (ordered or unordered)."""

    name: str = "list"
    type: str = "block"
    variant: str = "unordered"
    marker: str = "*"
    items: list[ListItemNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"items": self.items}

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "variant": self.variant,
            "marker": self.marker,
            "items": [i.to_dict() for i in self.items],
        }
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.title:
            data["title"] = self.title
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.List:
        node = ad_nodes.List(
            variant=self.variant,
            marker=self.marker,
            items=[i.to_node() for i in self.items],
        )
        node.attributes = dict(self.attributes)
        if self.title:
            node.title = ad_nodes.Title([ad_nodes.Text(self.title)])
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class DescriptionListTermNode(InlineNode):
    """Term element of a description list item."""

    name: str = "descriptionListTerm"
    type: str = "inline"
    inlines: list[BaseNode] = field(default_factory=list)

    def to_node(self) -> ad_nodes.DescriptionListTerm:
        node = ad_nodes.DescriptionListTerm(inlines=[i.to_node() for i in self.inlines])
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class DescriptionListItemNode(BlockNode):
    """Term-description item within a description list."""

    name: str = "descriptionListItem"
    type: str = "block"
    terms: list[DescriptionListTermNode] = field(default_factory=list)
    blocks: list[BaseNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        collections: dict[str, list[Any]] = {}
        if self.terms:
            collections["terms"] = self.terms
        if self.blocks:
            collections["blocks"] = self.blocks
        return collections

    def to_node(self) -> ad_nodes.DescriptionListItem:
        node = ad_nodes.DescriptionListItem(
            terms=[t.to_node() for t in self.terms],
            blocks=[b.to_node() for b in self.blocks],
        )
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class DescriptionListNode(BlockNode):
    """Description list block (term-description pairs)."""

    name: str = "descriptionList"
    type: str = "block"
    items: list[DescriptionListItemNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"items": self.items}

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "items": [i.to_dict() for i in self.items],
        }
        if self.attributes:
            data["attributes"] = dict(self.attributes)
        if self.title:
            data["title"] = self.title
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.DescriptionList:
        node = ad_nodes.DescriptionList(items=[i.to_node() for i in self.items])
        node.attributes = dict(self.attributes)
        if self.title:
            node.title = ad_nodes.Title([ad_nodes.Text(self.title)])
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class ImageNode(BlockNode):
    """Image directive node (block or inline)."""

    name: str = "image"
    type: str = "block"
    target: str = ""
    alt: str = ""
    form: str = "macro"
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def __post_init__(self) -> None:
        if self.alt and "alt" not in self.attributes:
            self.attributes["alt"] = self.alt
        elif not self.alt and "alt" in self.attributes:
            self.alt = str(self.attributes["alt"])

    def to_dict(self) -> dict[str, Any]:
        attrs = dict(self.attributes)
        if self.alt:
            attrs["alt"] = self.alt
        data: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "target": self.target,
            "form": self.form,
            "attributes": attrs,
        }
        if self.title:
            data["title"] = self.title
        if self.location is not None:
            data["location"] = self.location
        return data

    def to_node(self) -> ad_nodes.Image:
        node = ad_nodes.Image(target=self.target, alt=self.alt)
        node.form = self.form
        node.type = self.type
        node.attributes.update(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class BreakNode(InlineNode):
    """Hard line break node."""

    name: str = "break"
    type: str = "inline"
    location: Optional[list[dict[str, int]]] = None

    def to_node(self) -> ad_nodes.Break:
        node = ad_nodes.Break()
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class CalloutNode(InlineNode):
    """Callout marker node."""

    name: str = "callout"
    type: str = "inline"
    value: Union[int, str] = 1
    location: Optional[list[dict[str, int]]] = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["value"] = self.value
        return data

    def to_node(self) -> ad_nodes.Callout:
        num = int(self.value) if isinstance(self.value, (int, str)) and str(self.value).isdigit() else 1
        node = ad_nodes.Callout(num)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class LiteralNode(BlockNode):
    """Literal block preserving whitespace."""

    name: str = "literal"
    type: str = "block"
    code: str = ""
    inlines: list[BaseNode] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    delimiter: str = "...."
    title: Optional[str] = None
    form: str = "delimited"
    location: Optional[list[dict[str, int]]] = None

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"inlines": self.inlines} if self.inlines else {}

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["delimiter"] = self.delimiter
        data["form"] = self.form
        if self.code:
            data["value"] = self.code
        return data

    def to_node(self) -> ad_nodes.Literal:
        node = ad_nodes.Literal(
            inlines=[i.to_node() for i in self.inlines],
            attributes=dict(self.attributes),
            delimiter=self.delimiter,
        )
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class SidebarNode(BlockNode):
    """Sidebar block node."""

    name: str = "sidebar"
    type: str = "block"
    blocks: list[BaseNode] = field(default_factory=list)
    delimiter: str = "****"
    form: str = "delimited"
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["delimiter"] = self.delimiter
        data["form"] = self.form
        if self.title:
            data["title"] = self.title
        return data

    def to_node(self) -> ad_nodes.Sidebar:
        node = ad_nodes.Sidebar(
            blocks=[b.to_node() for b in self.blocks],
            delimiter=self.delimiter,
        )
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class QuoteNode(BlockNode):
    """Blockquote or verse block node."""

    name: str = "quote"
    type: str = "block"
    blocks: list[BaseNode] = field(default_factory=list)
    attribution: Optional[str] = None
    citetitle: Optional[str] = None
    delimiter: str = "____"
    form: str = "delimited"
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        if self.attribution:
            data["attribution"] = self.attribution
        if self.citetitle:
            data["citetitle"] = self.citetitle
        data["delimiter"] = self.delimiter
        data["form"] = self.form
        return data

    def to_node(self) -> ad_nodes.Quote:
        node = ad_nodes.Quote(
            blocks=[b.to_node() for b in self.blocks],
            delimiter=self.delimiter,
            attribution=self.attribution,
            citetitle=self.citetitle,
            attributes=dict(self.attributes),
        )
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class ExampleNode(BlockNode):
    """Example block node."""

    name: str = "example"
    type: str = "block"
    blocks: list[BaseNode] = field(default_factory=list)
    delimiter: str = "===="
    form: str = "delimited"
    attributes: dict[str, Any] = field(default_factory=dict)
    title: Optional[str] = None
    location: Optional[list[dict[str, int]]] = None

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["delimiter"] = self.delimiter
        data["form"] = self.form
        if self.title:
            data["title"] = self.title
        return data

    def to_node(self) -> ad_nodes.Example:
        node = ad_nodes.Example(
            blocks=[b.to_node() for b in self.blocks],
            delimiter=self.delimiter,
        )
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class ThematicBreakNode(BlockNode):
    """Thematic break / horizontal rule node."""

    name: str = "thematic_break"
    type: str = "block"
    location: Optional[list[dict[str, int]]] = None

    def to_node(self) -> ad_nodes.ThematicBreak:
        node = ad_nodes.ThematicBreak()
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class PageBreakNode(BlockNode):
    """Page break node."""

    name: str = "page_break"
    type: str = "block"
    location: Optional[list[dict[str, int]]] = None

    def to_node(self) -> ad_nodes.PageBreak:
        node = ad_nodes.PageBreak()
        if self.location is not None:
            node.location = self.location
        return node


@dataclass
class GenericNode(BaseNode):
    """Generic fallback node capturing arbitrary unmodeled ASG/AST structures."""

    data: dict[str, Any] = field(default_factory=dict)
    children_nodes: list[BaseNode] = field(default_factory=list)

    def get_child_collections(self) -> dict[str, list[Any]]:
        return {"children": self.children_nodes} if self.children_nodes else {}

    def to_dict(self) -> dict[str, Any]:
        res = dict(self.data)
        res["name"] = self.name
        res["type"] = self.type
        if self.attributes:
            res["attributes"] = dict(self.attributes)
        if self.location is not None:
            res["location"] = self.location
        if self.children_nodes:
            res["children"] = [c.to_dict() for c in self.children_nodes]
        return res

    def to_node(self) -> ad_nodes.Node:
        node = ad_nodes.Node(children=[c.to_node() for c in self.children_nodes])
        node.name = self.name
        node.type = self.type
        node.attributes = dict(self.attributes)
        if self.location is not None:
            node.location = self.location
        return node


# ---------------------------------------------------------------------------
# Bidirectional Factory & Conversion Functions
# ---------------------------------------------------------------------------


def node_from_dict(d: dict[str, Any]) -> BaseNode:
    """Construct a typed ASG model node from an ASG dictionary."""
    name = str(d.get("name", "")).lower()
    node_type = str(d.get("type", "block")).lower()
    attrs = dict(d.get("attributes", {})) if isinstance(d.get("attributes"), dict) else {}
    loc = d.get("location")

    if name == "document":
        blocks = [node_from_dict(b) for b in d.get("blocks", []) if isinstance(b, dict)]
        header: Optional[HeaderNode] = None
        if "header" in d and isinstance(d["header"], dict):
            raw_header = node_from_dict(d["header"])
            if isinstance(raw_header, HeaderNode):
                header = raw_header
        title = ""
        if "title" in d:
            title = _extract_plain_text(d["title"])
        elif header and header.title_text:
            title = header.title_text
        elif "doctitle" in attrs:
            title = str(attrs["doctitle"])
        docinfo = None
        if "docinfo" in d and isinstance(d["docinfo"], dict):
            docinfo = DocinfoNode(
                head_content=d["docinfo"].get("head_content", ""),
                footer_content=d["docinfo"].get("footer_content", ""),
            )
        return DocumentNode(
            title=title,
            blocks=blocks,
            header=header,
            docinfo=docinfo,
            footnotes=list(d.get("footnotes", [])),
            attributes=attrs,
            location=loc,
        )

    if name == "header":
        title_node = None
        if "title" in d and isinstance(d["title"], list):
            title_node = TitleNode(inlines=[node_from_dict(i) for i in d["title"] if isinstance(i, dict)])
        authors = []
        if "authors" in d and isinstance(d["authors"], list):
            for a in d["authors"]:
                if isinstance(a, dict) and "fullname" in a:
                    authors.append(AuthorNode(inlines=[TextNode(value=a["fullname"])]))
                elif isinstance(a, dict) and "inlines" in a:
                    authors.append(AuthorNode(inlines=[node_from_dict(i) for i in a["inlines"] if isinstance(i, dict)]))
        rev = None
        if "revision" in d and isinstance(d["revision"], dict):
            rev = RevisionNode(value=d["revision"].get("value", ""))
        docinfo = None
        if "docinfo" in d and isinstance(d["docinfo"], dict):
            docinfo = DocinfoNode(
                head_content=d["docinfo"].get("head_content", ""),
                footer_content=d["docinfo"].get("footer_content", ""),
            )
        return HeaderNode(
            title=title_node,
            authors=authors,
            revision=rev,
            docinfo=docinfo,
            attributes=attrs,
            location=loc,
        )

    if name == "section":
        blocks = [node_from_dict(b) for b in d.get("blocks", []) if isinstance(b, dict)]
        title_inlines = []
        if "title" in d:
            if isinstance(d["title"], list):
                title_inlines = [node_from_dict(i) for i in d["title"] if isinstance(i, dict)]
            elif isinstance(d["title"], str):
                title_inlines = [TextNode(value=d["title"])]
        title = _extract_plain_text(d.get("title", ""))
        return SectionNode(
            title=title,
            level=int(d.get("level", 1)),
            blocks=blocks,
            title_inlines=title_inlines,
            attributes=attrs,
            location=loc,
        )

    if name == "paragraph":
        inlines = [node_from_dict(i) for i in d.get("inlines", []) if isinstance(i, dict)]
        text = d.get("text") or _extract_plain_text(d.get("inlines", []))
        return ParagraphNode(
            text=str(text),
            inlines=inlines,
            attributes=attrs,
            title=d.get("title"),
            location=loc,
        )

    if name == "listing":
        inlines = [node_from_dict(i) for i in d.get("inlines", []) if isinstance(i, dict)]
        code = d.get("value") or _extract_plain_text(d.get("inlines", []))
        lang = str(attrs.get("language") or attrs.get("lang") or d.get("language", ""))
        return ListingNode(
            code=str(code),
            language=lang,
            inlines=inlines,
            attributes=attrs,
            delimiter=str(d.get("delimiter", "----")),
            title=d.get("title"),
            form=str(d.get("form", "delimited")),
            location=loc,
        )

    if name == "table":
        rows = [node_from_dict(r) for r in d.get("rows", []) if isinstance(r, dict)]
        typed_rows = [r for r in rows if isinstance(r, TableRowNode)]
        return TableNode(
            rows=typed_rows,
            columns=d.get("columns"),
            attributes=attrs,
            title=d.get("title"),
            location=loc,
        )

    if name == "row":
        cells = [node_from_dict(c) for c in d.get("cells", []) if isinstance(c, dict)]
        typed_cells = [c for c in cells if isinstance(c, TableCellNode)]
        return TableRowNode(
            cells=typed_cells,
            location=loc,
        )

    if name == "cell":
        blocks = [node_from_dict(b) for b in d.get("blocks", []) if isinstance(b, dict)]
        inlines = [node_from_dict(i) for i in d.get("inlines", []) if isinstance(i, dict)]
        text = _extract_plain_text(d.get("inlines", []))
        return TableCellNode(
            blocks=blocks,
            text=text,
            inlines=inlines,
            colspan=int(d.get("colspan", 1)),
            rowspan=int(d.get("rowspan", 1)),
            align=d.get("align"),
            valign=d.get("valign"),
            style=d.get("style"),
            attributes=attrs,
            location=loc,
        )

    if name == "admonition":
        blocks = [node_from_dict(b) for b in d.get("blocks", []) if isinstance(b, dict)]
        return AdmonitionNode(
            variant=str(d.get("variant", "NOTE")),
            blocks=blocks,
            delimiter=d.get("delimiter", "===="),
            form=str(d.get("form", "delimited")),
            attributes=attrs,
            title=d.get("title"),
            location=loc,
        )

    if name in ("floatingtitle", "discrete_heading", "discreteheading"):
        title_inlines = []
        if "title" in d:
            if isinstance(d["title"], list):
                title_inlines = [node_from_dict(i) for i in d["title"] if isinstance(i, dict)]
            elif isinstance(d["title"], str):
                title_inlines = [TextNode(value=d["title"])]
        title = _extract_plain_text(d.get("title", ""))
        return DiscreteHeadingNode(
            title=title,
            level=int(d.get("level", 1)),
            title_inlines=title_inlines,
            attributes=attrs,
            location=loc,
        )

    if name == "text":
        return TextNode(
            value=str(d.get("value", "")),
            location=loc,
        )

    if name == "span":
        inlines = [node_from_dict(i) for i in d.get("inlines", []) if isinstance(i, dict)]
        return SpanNode(
            variant=str(d.get("variant", "strong")),
            form=str(d.get("form", "constrained")),
            inlines=inlines,
            attributes=attrs,
            location=loc,
        )

    if name == "ref":
        inlines = [node_from_dict(i) for i in d.get("inlines", []) if isinstance(i, dict)]
        return RefNode(
            variant=str(d.get("variant", "link")),
            target=str(d.get("target", "")),
            inlines=inlines,
            resolved_strategy=d.get("resolved_strategy"),
            resolved_file_target=d.get("resolved_file_target"),
            resolved_anchor_target=d.get("resolved_anchor_target"),
            index=d.get("index"),
            attributes=attrs,
            location=loc,
        )

    if name == "list":
        items = [node_from_dict(i) for i in d.get("items", []) if isinstance(i, dict)]
        typed_items = [i for i in items if isinstance(i, ListItemNode)]
        return ListNode(
            variant=str(d.get("variant", "unordered")),
            marker=str(d.get("marker", "*")),
            items=typed_items,
            attributes=attrs,
            title=d.get("title"),
            location=loc,
        )

    if name in ("listitem", "list_item"):
        principal = [node_from_dict(p) for p in d.get("principal", []) if isinstance(p, dict)]
        blocks = [node_from_dict(b) for b in d.get("blocks", []) if isinstance(b, dict)]
        return ListItemNode(
            marker=str(d.get("marker", "*")),
            principal=principal,
            blocks=blocks,
            checked=d.get("checked"),
            attributes=attrs,
            location=loc,
        )

    if name == "image":
        return ImageNode(
            target=str(d.get("target", "")),
            alt=str(attrs.get("alt", "")),
            form=str(d.get("form", "macro")),
            attributes=attrs,
            title=d.get("title"),
            location=loc,
        )

    if name == "break":
        return BreakNode(location=loc)

    if name == "callout":
        return CalloutNode(value=d.get("value", 1), location=loc)

    if name == "literal":
        inlines = [node_from_dict(i) for i in d.get("inlines", []) if isinstance(i, dict)]
        code = d.get("value") or _extract_plain_text(d.get("inlines", []))
        return LiteralNode(
            code=str(code),
            inlines=inlines,
            attributes=attrs,
            delimiter=str(d.get("delimiter", "....")),
            title=d.get("title"),
            form=str(d.get("form", "delimited")),
            location=loc,
        )

    if name == "sidebar":
        blocks = [node_from_dict(b) for b in d.get("blocks", []) if isinstance(b, dict)]
        return SidebarNode(
            blocks=blocks,
            delimiter=str(d.get("delimiter", "****")),
            form=str(d.get("form", "delimited")),
            attributes=attrs,
            title=d.get("title"),
            location=loc,
        )

    if name == "quote":
        blocks = [node_from_dict(b) for b in d.get("blocks", []) if isinstance(b, dict)]
        return QuoteNode(
            blocks=blocks,
            attribution=d.get("attribution"),
            citetitle=d.get("citetitle"),
            delimiter=str(d.get("delimiter", "____")),
            form=str(d.get("form", "delimited")),
            attributes=attrs,
            title=d.get("title"),
            location=loc,
        )

    if name == "example":
        blocks = [node_from_dict(b) for b in d.get("blocks", []) if isinstance(b, dict)]
        return ExampleNode(
            blocks=blocks,
            delimiter=str(d.get("delimiter", "====")),
            form=str(d.get("form", "delimited")),
            attributes=attrs,
            title=d.get("title"),
            location=loc,
        )

    if name == "thematic_break":
        return ThematicBreakNode(location=loc)

    if name == "page_break":
        return PageBreakNode(location=loc)

    # Generic fallback
    children = [node_from_dict(c) for c in d.get("children", []) if isinstance(c, dict)]
    return GenericNode(
        name=name or "unknown",
        type=node_type,
        attributes=attrs,
        location=loc,
        data=d,
        children_nodes=children,
    )


def node_from_node(node: ad_nodes.Node) -> BaseNode:
    """Construct a typed ASG model node from an asciidoctrine AST Node."""
    if isinstance(node, ad_nodes.Document):
        header = node_from_node(node.header) if node.header else None
        title = ""
        if header and isinstance(header, HeaderNode) and header.title_text:
            title = header.title_text
        elif hasattr(node, "attributes") and "doctitle" in node.attributes:
            title = str(node.attributes["doctitle"])
        docinfo = None
        if hasattr(node, "docinfo") and node.docinfo:
            docinfo = DocinfoNode(
                head_content=getattr(node.docinfo, "head_content", ""),
                footer_content=getattr(node.docinfo, "footer_content", ""),
            )
        return DocumentNode(
            title=title,
            blocks=[node_from_node(b) for b in node.blocks],
            header=header if isinstance(header, HeaderNode) else None,
            docinfo=docinfo,
            footnotes=list(getattr(node, "footnotes", [])),
            attributes=dict(node.attributes),
            base_dir=node.base_dir,
            safe_mode=node.safe_mode,
            location=node.location,
        )

    if isinstance(node, ad_nodes.Header):
        title_node = None
        if node.title:
            title_node = TitleNode(inlines=[node_from_node(i) for i in node.title.inlines])
        authors = [AuthorNode(inlines=[node_from_node(i) for i in a.inlines]) for a in getattr(node, "authors", [])]
        rev = None
        if node.revision:
            rev = RevisionNode(
                value=node.revision.value,
                inlines=[node_from_node(i) for i in node.revision.inlines],
            )
        docinfo = None
        if hasattr(node, "docinfo") and node.docinfo:
            docinfo = DocinfoNode(
                head_content=getattr(node.docinfo, "head_content", ""),
                footer_content=getattr(node.docinfo, "footer_content", ""),
            )
        return HeaderNode(
            title=title_node,
            authors=authors,
            revision=rev,
            docinfo=docinfo,
            attributes=dict(node.attributes),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Section):
        title_inlines = []
        if node.title and hasattr(node.title, "inlines"):
            title_inlines = [node_from_node(i) for i in node.title.inlines]
        elif isinstance(node.title, list):
            title_inlines = [node_from_node(i) for i in node.title]
        sec_title = _extract_plain_text(node.title)
        return SectionNode(
            title=sec_title,
            level=node.level,
            blocks=[node_from_node(b) for b in node.blocks],
            title_inlines=title_inlines,
            attributes=dict(node.attributes),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Paragraph):
        inlines = [node_from_node(i) for i in node.inlines]
        text = _extract_plain_text(node.inlines)
        para_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return ParagraphNode(
            text=text,
            inlines=inlines,
            attributes=dict(node.attributes),
            title=para_title,
            location=node.location,
        )

    if isinstance(node, ad_nodes.Listing):
        inlines = [node_from_node(i) for i in node.inlines]
        code = getattr(node, "code", _extract_plain_text(node.inlines))
        lang = str(node.attributes.get("language") or node.attributes.get("lang", ""))
        listing_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return ListingNode(
            code=code,
            language=lang,
            inlines=inlines,
            attributes=dict(node.attributes),
            delimiter=getattr(node, "delimiter", "----"),
            title=listing_title,
            form=getattr(node, "form", "delimited"),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Table):
        rows = [node_from_node(r) for r in node.rows]
        typed_rows = [r for r in rows if isinstance(r, TableRowNode)]
        table_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return TableNode(
            rows=typed_rows,
            columns=node.columns,
            attributes=dict(node.attributes),
            title=table_title,
            location=node.location,
        )

    if isinstance(node, ad_nodes.TableRow):
        cells = [node_from_node(c) for c in node.cells]
        typed_cells = [c for c in cells if isinstance(c, TableCellNode)]
        return TableRowNode(
            cells=typed_cells,
            location=node.location,
        )

    if isinstance(node, ad_nodes.TableCell):
        blocks = [node_from_node(b) for b in node.blocks]
        return TableCellNode(
            blocks=blocks,
            text=_extract_plain_text(node.blocks),
            colspan=node.colspan,
            rowspan=node.rowspan,
            align=node.align,
            valign=node.valign,
            style=node.style,
            attributes=dict(node.attributes),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Admonition):
        admon_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return AdmonitionNode(
            variant=node.variant,
            blocks=[node_from_node(b) for b in node.blocks],
            delimiter=node.delimiter,
            form=getattr(node, "form", "delimited"),
            attributes=dict(node.attributes),
            title=admon_title,
            location=node.location,
        )

    ft_cls = getattr(ad_nodes, "FloatingTitle", None)
    if ft_cls is not None and isinstance(node, ft_cls):
        title_inlines = []
        if node.title and hasattr(node.title, "inlines"):
            title_inlines = [node_from_node(i) for i in node.title.inlines]
        heading_title = _extract_plain_text(node.title)
        return DiscreteHeadingNode(
            title=heading_title,
            level=getattr(node, "level", 1),
            title_inlines=title_inlines,
            attributes=dict(node.attributes),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Text):
        return TextNode(
            value=node.value,
            location=node.location,
        )

    if isinstance(node, ad_nodes.Span):
        return SpanNode(
            variant=node.variant,
            form=getattr(node, "form", "constrained"),
            inlines=[node_from_node(i) for i in node.inlines],
            attributes=dict(node.attributes),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Ref):
        return RefNode(
            variant=node.variant,
            target=node.target,
            inlines=[node_from_node(i) for i in node.inlines],
            resolved_strategy=node.resolved_strategy,
            resolved_file_target=node.resolved_file_target,
            resolved_anchor_target=node.resolved_anchor_target,
            index=node.index,
            attributes=dict(node.attributes),
            location=node.location,
        )

    if isinstance(node, ad_nodes.List):
        items = [node_from_node(i) for i in node.items]
        typed_items = [i for i in items if isinstance(i, ListItemNode)]
        list_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return ListNode(
            variant=node.variant,
            marker=node.marker,
            items=typed_items,
            attributes=dict(node.attributes),
            title=list_title,
            location=node.location,
        )

    if isinstance(node, ad_nodes.ListItem):
        principal = [node_from_node(p) for p in node.principal]
        blocks = [node_from_node(b) for b in node.blocks]
        return ListItemNode(
            marker=node.marker,
            principal=principal,
            blocks=blocks,
            checked=node.checked,
            attributes=dict(node.attributes),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Image):
        alt = node.attributes.get("alt", "")
        return ImageNode(
            target=node.target,
            alt=alt,
            form=getattr(node, "form", "macro"),
            attributes=dict(node.attributes),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Break):
        return BreakNode(location=node.location)

    if isinstance(node, ad_nodes.Callout):
        return CalloutNode(value=getattr(node, "value", 1), location=node.location)

    if isinstance(node, ad_nodes.Literal):
        inlines = [node_from_node(i) for i in node.inlines]
        code = getattr(node, "code", _extract_plain_text(node.inlines))
        literal_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return LiteralNode(
            code=code,
            inlines=inlines,
            attributes=dict(node.attributes),
            delimiter=getattr(node, "delimiter", "...."),
            title=literal_title,
            form=getattr(node, "form", "delimited"),
            location=node.location,
        )

    if isinstance(node, ad_nodes.Sidebar):
        sidebar_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return SidebarNode(
            blocks=[node_from_node(b) for b in node.blocks],
            delimiter=getattr(node, "delimiter", "****"),
            form=getattr(node, "form", "delimited"),
            attributes=dict(node.attributes),
            title=sidebar_title,
            location=node.location,
        )

    if isinstance(node, ad_nodes.Quote):
        quote_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return QuoteNode(
            blocks=[node_from_node(b) for b in node.blocks],
            attribution=getattr(node, "attribution", None),
            citetitle=getattr(node, "citetitle", None),
            delimiter=getattr(node, "delimiter", "____"),
            form=getattr(node, "form", "delimited"),
            attributes=dict(node.attributes),
            title=quote_title,
            location=node.location,
        )

    if isinstance(node, ad_nodes.Example):
        example_title = _extract_plain_text(node.title) if getattr(node, "title", None) else None
        return ExampleNode(
            blocks=[node_from_node(b) for b in node.blocks],
            delimiter=getattr(node, "delimiter", "===="),
            form=getattr(node, "form", "delimited"),
            attributes=dict(node.attributes),
            title=example_title,
            location=node.location,
        )

    if isinstance(node, ad_nodes.ThematicBreak):
        return ThematicBreakNode(location=node.location)

    if isinstance(node, ad_nodes.PageBreak):
        return PageBreakNode(location=node.location)

    # Fallback to converting via to_dict() if available
    if hasattr(node, "to_dict"):
        return node_from_dict(node.to_dict())

    return GenericNode(
        name=getattr(node, "name", "unknown"),
        type=getattr(node, "type", "block"),
        attributes=dict(getattr(node, "attributes", {})),
        location=getattr(node, "location", None),
    )


def asg_to_model(data: Union[dict[str, Any], ad_nodes.Node, BaseNode]) -> BaseNode:
    """Universal adapter converting ASG dict, asciidoctrine Node, or BaseNode into a typed BaseNode."""
    if isinstance(data, BaseNode):
        return data
    if isinstance(data, dict):
        return node_from_dict(data)
    if isinstance(data, ad_nodes.Node):
        return node_from_node(data)
    raise TypeError(f"Cannot convert object of type {type(data).__name__} to BaseNode")


def model_to_asg(model: BaseNode) -> dict[str, Any]:
    """Serialize a typed BaseNode model into an ASG-compatible dictionary."""
    return model.to_dict()


def model_to_node(model: BaseNode) -> ad_nodes.Node:
    """Convert a typed BaseNode model into an asciidoctrine AST Node."""
    return model.to_node()
