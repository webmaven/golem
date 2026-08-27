"""
HTML rendering pipeline for Golem — body content, TOC, and ASG traversal utilities.

This module is the bridge between the parsed document representation
(ASG dict or AST Node from ``asciidoctrine``) and the final HTML markup
that the Chameleon template layer wraps into a full page.

=== Main responsibilities

- `render_body` — delegates to ``asciidoctype.AsciiDoctypeRenderer``
  to convert an ASG dict into the inner HTML of the ``<main>`` content
  area, with special handling for document-level footnote rendering.
- `generate_toc_html` — traverses the section tree and produces a
  ``<nav class="toc">`` element for sidebar or inline TOC use.
- `collect_node_types` — walks the ASG to extract the set of node
  names present in a document (used by the engine to fingerprint which
  template partials a page depends on, enabling scoped cache invalidation).

=== Internal helpers

- `_slugify` — converts arbitrary text to a URL/HTML-id-safe slug.
- `_ensure_section_ids` — recursively assigns ``id`` attributes to
  every section node that lacks one, deriving them from the section title
  via `_slugify`.
- `_extract_plain_text` — recursively extracts the concatenated
  plain-text content from nested inline or block nodes (used for TOC
  link labels and section ID generation).
- `_collect_sections` — recursively accumulates all section nodes
  from an ASG tree for TOC construction.
"""

import re
from pathlib import Path
from typing import Any, List, Optional, Union
import asciidoctype  # type: ignore[import-untyped]
from asciidoctrine.nodes import Node


def render_body(
    asg_root: Union[Node, dict[str, Any]],
    search_paths: Optional[List[Path]] = None,
) -> str:
    """Render an ASG dictionary or AST Node structure into static HTML5 markup.

    Constructs an :class:`asciidoctype.AsciiDoctypeRenderer` instance,
    optionally seeded with *search_paths* for template override lookup,
    then dispatches rendering based on the root node type:

    - **document node** — renders each top-level block separately and
      concatenates the results, then appends a ``<div id="footnotes">``
      block if the document has footnote definitions.
    - **any other node** — renders the single node directly.

    Section IDs are guaranteed before rendering via
    :func:`_ensure_section_ids`, so every ``<h2>``–``<h6>`` in the
    output has a stable ``id`` attribute that TOC anchors can target.

    Template context construction
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    The renderer itself does not build a Chameleon template context;
    that is the responsibility of :class:`golem.templates.PageCompiler`.
    ``render_body`` produces only the *inner* content string
    (``body_content``) that ``PageCompiler`` injects into the
    ``skeleton.pt`` layout template.

    === Arguments

    - ``asg_root``:: ASG dictionary representation (a ``dict`` whose root
      has ``"name": "document"``) or an ``asciidoctrine`` AST Node.
    - ``search_paths``:: Optional list of :class:`~pathlib.Path` objects
      passed to ``AsciiDoctypeRenderer`` for project-local template
      partial overrides.

    === Returns

    Rendered inner HTML5 markup string ready for injection into the
    ``skeleton.pt`` layout.

    === Raises

    ``TypeError``
        If *asg_root* is neither a ``dict`` nor an object with a
        ``to_dict()`` method.
    """
    if hasattr(asg_root, "to_dict"):
        node_dict = asg_root.to_dict()
    elif isinstance(asg_root, dict):
        node_dict = asg_root
    else:
        raise TypeError(f"Expected Node or dict, got {type(asg_root).__name__}")

    _ensure_section_ids(node_dict)
    renderer = asciidoctype.AsciiDoctypeRenderer(search_paths=search_paths)
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
    """Generate a clean URL-friendly and HTML id-friendly slug from text."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _ensure_section_ids(node: Any) -> None:
    """Recursively ensure every section node has an id attribute based on its title."""
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
    """Recursively traverse node trees and collect section elements."""
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
    """Traverse the document section tree and emit a ``<nav class="toc">`` HTML element.

    Calls :func:`_ensure_section_ids` first so every section anchor is
    stable, then collects all section nodes via :func:`_collect_sections`
    and iterates over them in document order.

    Nesting algorithm
    ~~~~~~~~~~~~~~~~~
    The generator tracks a ``current_level`` cursor and emits opening
    ``<ul class="toc-level-N">`` elements as level increases and closing
    ``</ul>`` elements as level decreases, producing a correctly nested
    multi-level tree.  The base level of the first section is used as the
    reference; sections with a level lower than the base are clamped to
    the base to handle documents where the first section is not a top-
    level ``==`` heading.

    === Arguments

    - ``asg_root``:: ASG dictionary representation (root ``dict`` with
      ``"name": "document"``) or an ``asciidoctrine`` AST Node.

    === Returns

    Rendered ``<nav class="toc">…</nav>`` HTML string, or ``""`` if the
    document has no sections.
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
    """Extract all unique ASG/AST node names present in a document tree.

    Performs a depth-first walk of the full node hierarchy — handling
    both the ``dict``-based ASG representation and object-based AST nodes
    — and accumulates every distinct lowercase node name (e.g.
    ``"listing"``, ``"table"``, ``"section"``, ``"admonition"``) into a
    set, then returns it sorted.

    Primary use case
    ~~~~~~~~~~~~~~~~
    The build engine calls this after rendering each page and stores the
    result in ``cache_data["metadata"][path]["node_types"]``.  When a
    theme template partial is updated, the engine compares the partial
    name against each page's stored node types to determine which pages
    need to be rebuilt — avoiding a full site rebuild when, for example,
    only the ``listing`` partial changes.

    Traversal strategy
    ~~~~~~~~~~~~~~~~~~
    For ``dict`` nodes, the traversal recurses into the following child
    collection keys (when present): ``"blocks"``, ``"children"``,
    ``"items"``, ``"inlines"``, ``"title"``, ``"rows"``, ``"cells"``,
    ``"footnotes"``, ``"header"``.

    For object nodes, the same attribute names are tried plus
    ``get_child_collections()`` when available (for AST nodes that
    expose their children through a method rather than attributes).

    === Arguments

    - ``asg_root``:: ASG dictionary representation or ``asciidoctrine``
      AST Node for the document to inspect.

    === Returns

    Sorted ``list[str]`` of unique node name strings found anywhere in
    the document tree.
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
