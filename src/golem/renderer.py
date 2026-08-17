"""
= HTML Rendering Engine

This module provides the static HTML rendering interface for Golem, delegating
document and node translation directly to `asciidoctype.AsciiDoctypeRenderer`
and generating clean Table of Contents navigation trees.
"""

from pathlib import Path
from typing import Any, List, Optional, Union
import asciidoctype  # type: ignore[import-untyped]
from asciidoctrine.nodes import Node


def render_body(
    asg_root: Union[Node, dict[str, Any]],
    search_paths: Optional[List[Path]] = None,
) -> str:
    """
    == render_body

    Render an ASG dictionary or AST Node structure into static HTML5 markup.

    === Arguments

    - `asg_root`:: ASG dictionary representation or AST Node.
    - `search_paths`:: Optional list of template directory paths for overrides.

    === Returns

    Rendered HTML5 markup string.
    """
    if hasattr(asg_root, "to_dict"):
        node_dict = asg_root.to_dict()
    elif isinstance(asg_root, dict):
        node_dict = asg_root
    else:
        raise TypeError(f"Expected Node or dict, got {type(asg_root).__name__}")

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


def _extract_plain_text(node: Any) -> str:
    """Extract recursively concatenated plain text from inlines, nodes, or dictionaries."""
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
    """
    == generate_toc_html

    Traverse sections in ASG dictionaries or AST nodes and build a clean `<nav class="toc">` HTML.

    === Arguments

    - `asg_root`:: ASG dictionary representation or AST Node.

    === Returns

    Rendered HTML5 Table of Contents or empty string if no sections exist.
    """
    sections: list[Any] = []
    _collect_sections(asg_root, sections)
    if not sections:
        return ""

    base_level = (
        sections[0].get("level", 1)
        if isinstance(sections[0], dict)
        else getattr(sections[0], "level", 1)
    )
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
            anchor_id = title_str.lower().replace(" ", "-").replace("_", "-")

        if level < base_level:
            level = base_level

        if first:
            toc_parts.append(
                f'  <li class="toc-item level-{level}"><a href="#{anchor_id}">{title_str}</a>'
            )
            first = False
        else:
            if level > current_level:
                while current_level < level:
                    toc_parts.append(
                        f'\n  <ul class="toc-level-{current_level + 1}">\n'
                    )
                    current_level += 1
                toc_parts.append(
                    f'  <li class="toc-item level-{level}"><a href="#{anchor_id}">{title_str}</a>'
                )
            elif level < current_level:
                while current_level > level:
                    toc_parts.append("</li>\n  </ul>\n")
                    current_level -= 1
                toc_parts.append(
                    f'</li>\n  <li class="toc-item level-{level}"><a href="#{anchor_id}">{title_str}</a>'
                )
            else:
                toc_parts.append(
                    f'</li>\n  <li class="toc-item level-{level}"><a href="#{anchor_id}">{title_str}</a>'
                )

    while current_level > base_level:
        toc_parts.append("</li>\n  </ul>\n")
        current_level -= 1
    toc_parts.append("</li>\n</ul>\n</nav>")
    return "".join(toc_parts)
