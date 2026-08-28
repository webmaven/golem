"""Provide static HTML rendering and Table of Contents generation for Golem.

== Rendering Pipeline

Golem's rendering pipeline converts structured document models (either raw
`asciidoctrine` AST nodes or resolved ASG dictionaries) into semantic HTML5 markup:

1. Section ID Normalization:: Ensures every section heading possesses a unique,
   deterministic slug identifier for stable anchor linking (`_ensure_section_ids`).
2. Template Delegation:: Delegates AST/ASG node translation directly to
   `asciidoctype.AsciiDoctypeRenderer`, supporting custom template search paths
   for layout and block component overrides.
3. Document & Footnote Assembly:: For root `document` nodes, sequentially renders
   top-level block nodes and generates a dedicated HTML5 `<div id="footnotes">`
   section containing backlinked footnote references.
4. Node Type Discovery:: Scans node trees to discover active node types (`collect_node_types`),
   enabling fine-grained cache invalidation and template mapping.

== AsciiDoctype Integration

Document and block translation delegates to `asciidoctype.AsciiDoctypeRenderer`.
Custom template directories can be passed via `search_paths` to override default
template mappings for specific AsciiDoc AST/ASG node types (such as paragraphs, listings,
admonitions, and tables).

== Table of Contents (TOC) Extraction

Table of Contents generation (`generate_toc_html`) traverses document sections,
normalizes headings using slugified anchor targets, and constructs a nested `<nav class="toc">`
HTML structure that mirrors the hierarchical document outline.
"""

import re
from pathlib import Path
from typing import Any, Callable, List, Optional, Union
import asciidoctype  # type: ignore[import-untyped]
from asciidoctrine.nodes import Node
from golem.highlighting import make_highlighter


def render_body(
    asg_root: Union[Node, dict[str, Any]],
    search_paths: Optional[List[Path]] = None,
    highlighter: Optional[Callable[[str, str], Optional[str]]] = None,
) -> str:
    """Render an ASG dictionary or AST Node structure into static HTML5 markup.

    Accepts an `asciidoctrine.nodes.Node` instance or an Abstract Semantic Graph (ASG)
    dictionary, ensures all contained sections possess deterministic slug IDs, and translates
    the node structure into HTML5 markup via `asciidoctype.AsciiDoctypeRenderer`.

    When rendering a root `document` node, individual child blocks are rendered sequentially
    and any collected document footnotes are compiled into a trailing `<div id="footnotes">`
    block with backlinking anchor tags. For non-document nodes or fragments, the node is
    rendered directly.

    [parameters]
    `asg_root` (Node | dict[str, Any]):: AST Node or ASG dictionary representation of the document or fragment.
    `search_paths` (list[Path] | None, optional):: Optional list of directory paths containing custom Chameleon template overrides. Defaults to `None`.
    `highlighter` (Callable[[str, str], Optional[str]] | None, optional):: Optional syntax highlighter callable. Defaults to default Fired Clay Pygments highlighter.

    [returns]
    `str`:: Rendered HTML5 markup string.

    [raises]
    `TypeError`:: If `asg_root` is neither an AST `Node` nor a `dict`.
    """
    if hasattr(asg_root, "to_dict"):
        node_dict = asg_root.to_dict()
    elif isinstance(asg_root, dict):
        node_dict = asg_root
    else:
        raise TypeError(f"Expected Node or dict, got {type(asg_root).__name__}")

    _ensure_section_ids(node_dict)
    active_highlighter = highlighter if highlighter is not None else make_highlighter()
    renderer = asciidoctype.AsciiDoctypeRenderer(
        search_paths=search_paths,
        highlighter=active_highlighter,
    )
    if node_dict.get("name") == "document":
        blocks = node_dict.get("blocks", [])
        rendered_blocks = [renderer.render(block) for block in blocks]
        footnotes = node_dict.get("footnotes", [])
        if footnotes:
            fn_parts = ['<div id="footnotes">\n  <hr />']
            for fn in footnotes:
                fn_num = fn.get("index", fn.get("number", ""))
                fn_id = fn.get("id") or fn_num
                if fn.get("inlines"):
                    fn_content = "".join(renderer.render(inl) for inl in fn["inlines"])
                else:
                    fn_content = str(fn.get("text", fn.get("value", "")))
                fn_parts.append(
                    f'  <div class="footnote" id="_footnotedef_{fn_num}">\n'
                    f'    <a href="#_footnote_{fn_id}">{fn_num}</a>. {fn_content}\n'
                    f"  </div>"
                )
            fn_parts.append("</div>")
            rendered_blocks.append("\n".join(fn_parts))
        return "\n".join(rendered_blocks)
    return renderer.render(node_dict)


def _slugify(text: str) -> str:
    """Generate a clean URL-friendly and HTML id-friendly slug from text.

    Transforms input text by converting characters to lowercase, trimming leading and
    trailing whitespace, replacing non-alphanumeric character sequences with hyphens,
    and stripping leading or trailing hyphens.

    [parameters]
    `text` (str):: Source text string to convert into an identifier slug.

    [returns]
    `str`:: Sanitized hyphen-delimited slug string suitable for HTML `id` attributes and URLs.
    """
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _ensure_section_ids(node: Any) -> None:
    """Recursively ensure every section node has an id attribute based on its title.

    Traverses an AST Node, ASG dictionary, or collection of nodes in-place. When a `section`
    node without an existing `id` attribute is encountered, its title text is extracted
    via `_extract_plain_text` and converted into a slugified identifier via `_slugify`.

    NOTE: Modifies node attribute dictionaries or object attributes in-place.

    [parameters]
    `node` (Any):: AST Node, ASG dictionary, list of nodes, or nested node tree to process.
    """
    if not node:
        return
    if isinstance(node, list):
        for item in node:
            _ensure_section_ids(item)
        return
    if isinstance(node, dict):
        if node.get("name") == "section":
            attrs = node.setdefault("attributes", {})
            if isinstance(attrs, dict) and not attrs.get("id"):
                title_nodes = node.get("title", [])
                title_str = _extract_plain_text(title_nodes)
                if title_str:
                    attrs["id"] = _slugify(title_str)
        for key in ("blocks", "children", "items"):
            if key in node and isinstance(node[key], list):
                for child in node[key]:
                    _ensure_section_ids(child)
        return

    name = getattr(node, "name", "") or node.__class__.__name__.lower()
    if name == "section":
        attrs = getattr(node, "attributes", None)
        if isinstance(attrs, dict) and not attrs.get("id"):
            title_nodes = getattr(node, "title", [])
            title_str = _extract_plain_text(title_nodes)
            if title_str:
                attrs["id"] = _slugify(title_str)
    if hasattr(node, "blocks") and node.blocks:
        for child in node.blocks:
            _ensure_section_ids(child)
    elif hasattr(node, "children") and node.children:
        for child in node.children:
            _ensure_section_ids(child)
    elif hasattr(node, "items") and node.items:
        for child in node.items:
            _ensure_section_ids(child)


def _extract_plain_text(node: Any) -> str:
    """Recursively extract plain string representations from nested inlines or AST nodes.

    Traverses string literals, lists, dictionaries, or AST `Node` instances to extract
    and concatenate plain text content from `value`, `text`, `inlines`, `children`,
    `title`, or child collections while ignoring structural markup.

    [parameters]
    `node` (Any):: AST Node, ASG dictionary, list of nodes, string, or primitive value to extract text from.

    [returns]
    `str`:: Concatenated plain text string extracted from the node hierarchy.
    """
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
    if hasattr(node, "title") and node.title:
        res.append(_extract_plain_text(node.title))
    if hasattr(node, "get_child_collections"):
        for collection in node.get_child_collections().values():
            for child in collection:
                res.append(_extract_plain_text(child))
    elif hasattr(node, "children") and node.children:
        for child in node.children:
            res.append(_extract_plain_text(child))
    return "".join(res)


def _collect_sections(node: Any, sections: list) -> None:
    """Recursively traverse node trees and collect section elements.

    Traverses an AST Node, ASG dictionary, or list structure in document order,
    identifying all `section` elements across blocks, children, items, and collections,
    and appending them to the provided accumulator list.

    [parameters]
    `node` (Any):: AST Node, ASG dictionary, or list representing the root or branch of the node tree.
    `sections` (list[Any]):: Mutable list to which encountered section nodes are appended.
    """
    if not node:
        return
    if isinstance(node, list):
        for item in node:
            _collect_sections(item, sections)
        return
    if isinstance(node, dict):
        if node.get("name") == "section":
            sections.append(node)
        for key in ("blocks", "children", "items"):
            if key in node and isinstance(node[key], list):
                for child in node[key]:
                    _collect_sections(child, sections)
        return

    name = getattr(node, "name", "") or node.__class__.__name__.lower()
    if name == "section":
        sections.append(node)
    if hasattr(node, "blocks") and node.blocks:
        for child in node.blocks:
            _collect_sections(child, sections)
    elif hasattr(node, "children") and node.children:
        for child in node.children:
            _collect_sections(child, sections)
    elif hasattr(node, "items") and node.items:
        for child in node.items:
            _collect_sections(child, sections)
    elif hasattr(node, "get_child_collections"):
        for collection in node.get_child_collections().values():
            for child in collection:
                _collect_sections(child, sections)


def generate_toc_html(asg_root: Union[Node, dict[str, Any]]) -> str:
    """Traverse sections in ASG dictionaries or AST nodes and build a clean Table of Contents HTML navigation tree.

    Recursively discovers all sections within the document tree, ensures section anchor IDs
    are populated, and constructs a structured HTML5 `<nav class="toc">` element containing
    nested unordered lists (`<ul class="toc-list">`, `<ul class="toc-level-N">`) reflecting
    the document's hierarchical section depth.

    If no sections are found in the document, an empty string is returned.

    [parameters]
    `asg_root` (Node | dict[str, Any]):: AST Node or ASG dictionary representation of the document.

    [returns]
    `str`:: Rendered HTML5 Table of Contents markup, or an empty string if no sections exist.
    """
    _ensure_section_ids(asg_root)
    sections: list[Any] = []
    _collect_sections(asg_root, sections)
    if not sections:
        return ""

    base_level = sections[0].get("level", 1) if isinstance(sections[0], dict) else getattr(sections[0], "level", 1)
    toc_parts: list[str] = ['<nav class="toc">\n<ul class="toc-list">\n']
    current_level = base_level
    first = True

    for sec in sections:
        if isinstance(sec, dict):
            level = sec.get("level", 1)
            title_nodes = sec.get("title", [])
            attrs = sec.get("attributes", {})
            anchor_id = attrs.get("id") if isinstance(attrs, dict) else None
        else:
            level = getattr(sec, "level", 1)
            title_nodes = getattr(sec, "title", [])
            attrs = getattr(sec, "attributes", {})
            anchor_id = attrs.get("id") if isinstance(attrs, dict) else None

        title_str = _extract_plain_text(title_nodes)
        if not anchor_id:
            anchor_id = _slugify(title_str)

        if level < base_level:
            level = base_level

        if first:
            toc_parts.append(f'  <li class="toc-item level-{level}"><a href="#{anchor_id}">{title_str}</a>')
            first = False
        else:
            if level > current_level:
                while current_level < level:
                    toc_parts.append(f'\n  <ul class="toc-level-{current_level + 1}">\n')
                    current_level += 1
                toc_parts.append(f'  <li class="toc-item level-{level}"><a href="#{anchor_id}">{title_str}</a>')
            elif level < current_level:
                while current_level > level:
                    toc_parts.append("</li>\n  </ul>\n")
                    current_level -= 1
                toc_parts.append(f'</li>\n  <li class="toc-item level-{level}"><a href="#{anchor_id}">{title_str}</a>')
            else:
                toc_parts.append(f'</li>\n  <li class="toc-item level-{level}"><a href="#{anchor_id}">{title_str}</a>')

    while current_level > base_level:
        toc_parts.append("</li>\n  </ul>\n")
        current_level -= 1
    toc_parts.append("</li>\n</ul>\n</nav>")
    return "".join(toc_parts)


def collect_node_types(asg_root: Union[Node, dict[str, Any]]) -> list[str]:
    """Extract all unique AST and ASG node names found in a document or node tree.

    Recursively walks all branches of an AST Node or ASG dictionary tree—including blocks,
    children, items, inlines, title nodes, table rows, cells, headers, and footnotes—to collect
    every distinct node type name.

    The resulting list of node type names is used by the build engine to map template
    dependencies and determine granular cache invalidation triggers.

    [parameters]
    `asg_root` (Node | dict[str, Any]):: AST Node or ASG dictionary tree to inspect.

    [returns]
    `list[str]`:: Sorted list of unique lowercase node type names present in the tree.
    """
    node_types: set[str] = set()

    def _traverse(node: Any) -> None:
        if not node:
            return
        if isinstance(node, list):
            for item in node:
                _traverse(item)
            return
        if isinstance(node, dict):
            name = node.get("name")
            if name and isinstance(name, str):
                node_types.add(name.lower())
            for key in ("blocks", "children", "items", "inlines", "title", "rows", "cells", "footnotes", "header"):
                if key in node and node[key] is not None:
                    _traverse(node[key])
            return

        name = getattr(node, "name", "") or (node.__class__.__name__.lower() if hasattr(node, "__class__") else "")
        if name and isinstance(name, str):
            node_types.add(name.lower())

        if hasattr(node, "get_child_collections"):
            try:
                collections = node.get_child_collections()
                if isinstance(collections, dict):
                    for collection in collections.values():
                        _traverse(collection)
            except Exception:
                pass

        for attr in ("blocks", "children", "items", "inlines", "title", "rows", "cells", "footnotes", "header"):
            if hasattr(node, attr):
                val = getattr(node, attr)
                if val is not None:
                    _traverse(val)

    _traverse(asg_root)
    return sorted(node_types)
