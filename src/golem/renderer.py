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


DEFAULT_TEMPLATES_DIR: Path = Path(__file__).parent / "templates" / "default"


class GolemRenderer(asciidoctype.AsciiDoctypeRenderer):
    """AsciiDoctypeRenderer subclass with Golem-specific multi-view extensions."""

    def get_derived_views(
        self,
        node: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, str]]:
        """Extract multi-view derived representations for a listing node."""
        from golem.views import extract_listing_views

        return extract_listing_views(node, highlighter=self.highlighter)

    def get_listing_roles(self, node: dict[str, Any]) -> list[str]:
        """Extract and sanitize role identifiers for listing badges.

        Filters role attributes to permit only safe alphanumeric characters,
        hyphens, and underscores to prevent CSS/HTML injection.
        """
        if not isinstance(node, dict):
            return []
        attrs = node.get("attributes")
        role_attr = attrs.get("role") if isinstance(attrs, dict) else node.get("role")
        if not role_attr:
            return []
        if isinstance(role_attr, str):
            raw_roles = role_attr.split()
        elif isinstance(role_attr, (list, tuple, set)):
            raw_roles = [str(r) for r in role_attr]
        else:
            raw_roles = [str(role_attr)]

        sanitized: list[str] = []
        for r in raw_roles:
            cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", r)
            if cleaned and cleaned not in sanitized:
                sanitized.append(cleaned)
        return sanitized

    def highlight_code(
        self,
        node: dict[str, Any],
        ctx: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """Highlight code with callout markers re-injected into the output.

        Overrides `AsciiDoctypeRenderer.highlight_code` to handle listing nodes
        whose ``inlines`` list contains a mix of ``text`` and ``callout`` nodes.
        The parent implementation calls ``extract_text``, which silently drops
        ``callout`` inlines because their ``value`` is an integer rather than a
        string. This override:

        1. Detects whether any ``callout`` inlines are present.
        2. If so, separates text segments from callout markers, tracks the line
           number at which each callout occurs (by counting newlines accumulated
           in the text segments preceding it), and highlights only the clean code.
        3. After Pygments produces the highlighted HTML, splits the ``<code>``
           inner content on newlines and appends
           ``<i class="conum" data-value="N"><b>N</b></i>`` at each callout line.
        4. Falls back to the parent implementation unchanged when there are no
           callout inlines.

        [parameters]
        `node` (dict[str, Any]):: ASG listing node dictionary.
        `ctx` (dict[str, Any] | None, optional):: Template rendering context.

        [returns]
        `str | None`:: Highlighted HTML with callout badges, or ``None`` when no
        highlighter is configured or the language is unrecognised.
        """
        if self.highlighter is None:
            return None

        inlines = node.get("inlines") if isinstance(node, dict) else None
        if not isinstance(inlines, list):
            return super().highlight_code(node, ctx)

        has_callouts = any(isinstance(il, dict) and il.get("name") == "callout" for il in inlines)
        if not has_callouts:
            return super().highlight_code(node, ctx)

        # --- Separate text from callout inlines ---
        code_parts: list[str] = []
        # Maps 0-based line number → list of callout values at that line
        callout_positions: dict[int, list] = {}
        for inline in inlines:
            if not isinstance(inline, dict):
                continue
            if inline.get("name") == "callout":
                line_num = "".join(code_parts).count("\n")
                val = inline.get("value", "")
                callout_positions.setdefault(line_num, []).append(val)
            else:
                raw = inline.get("value", "")
                if isinstance(raw, str):
                    code_parts.append(raw)

        code = "".join(code_parts)

        # Resolve language the same way the parent does
        attrs = node.get("attributes") if isinstance(node, dict) else {}
        lang: str = ""
        if isinstance(attrs, dict):
            lang = attrs.get("language") or attrs.get("lang") or ""
        if not lang:
            lang = (node.get("language") or "") if isinstance(node, dict) else ""

        highlighted = self.highlighter(code, str(lang))
        if highlighted is None:
            return None

        if not callout_positions:
            return highlighted

        # --- Inject callout badges into the highlighted HTML ---
        # make_highlighter output: <pre class="highlight LANG"><code class="language-LANG">CONTENT</code></pre>
        m = re.search(
            r"(<pre[^>]*><code[^>]*>)(.*)(</code></pre>)",
            highlighted,
            re.DOTALL,
        )
        if not m:
            return highlighted

        pre_open, content, pre_close = m.group(1), m.group(2), m.group(3)
        lines = content.split("\n")
        for line_num, vals in callout_positions.items():
            if 0 <= line_num < len(lines):
                for val in vals:
                    safe_val = re.sub(r"[^0-9]", "", str(val))
                    lines[line_num] += f'<i class="conum" data-value="{safe_val}"><b>{safe_val}</b></i>'
        return pre_open + "\n".join(lines) + pre_close

    def render_view_content(self, view: dict[str, Any]) -> str:
        """Render raw HTML content for a validated derived view tab."""
        return str(view.get("content", ""))


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
    `search_paths` (list[Path] | None, optional):: Optional list of directory paths containing custom Chameleon template overrides. Defaults to including `src/golem/templates/default`.
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
    _reattach_block_titles(node_dict)
    active_highlighter = highlighter if highlighter is not None else make_highlighter()
    active_search_paths: list[Path] = []
    if search_paths:
        active_search_paths.extend(search_paths)
    if DEFAULT_TEMPLATES_DIR.exists() and DEFAULT_TEMPLATES_DIR not in active_search_paths:
        active_search_paths.append(DEFAULT_TEMPLATES_DIR)

    renderer = GolemRenderer(
        search_paths=active_search_paths,
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


def _is_block_title_paragraph(block: dict[str, Any]) -> bool:
    """Return True if a paragraph block is an orphaned AsciiDoc block title.

    Detects the asciidoctrine parser limitation where a block title line
    (``.Title``) following another block is parsed as a standalone paragraph
    instead of being attached as the ``title`` attribute of the following block.
    A paragraph qualifies as an orphaned block title when it has exactly one
    text-type inline whose value begins with a single ``.`` followed by
    non-whitespace content.

    [parameters]
    `block` (dict[str, Any]):: ASG node dictionary to inspect.

    [returns]
    `bool`:: ``True`` if the block is an orphaned block-title paragraph.
    """
    if not isinstance(block, dict) or block.get("name") != "paragraph":
        return False
    inlines = block.get("inlines", [])
    if len(inlines) != 1:
        return False
    inline = inlines[0]
    if not isinstance(inline, dict):
        return False
    value = inline.get("value", "")
    return isinstance(value, str) and value.startswith(".") and len(value) > 1 and not value[1:2].isspace()


def _reattach_block_titles(node: Any) -> None:
    """Post-process an ASG dictionary to reattach orphaned block-title paragraphs.

    Fixes an ``asciidoctrine`` parser limitation where block titles (``.Title``
    syntax) appearing after other blocks are parsed as standalone paragraphs
    instead of being attached as the ``title`` attribute of the following block.
    This pass traverses all block lists recursively and, for each consecutive
    pair where the first block is an orphaned block-title paragraph (detected
    via `_is_block_title_paragraph`) and the second block has no title, strips
    the leading ``.`` from the first inline's value, promotes the remaining
    inlines as the ``title`` of the second block, and removes the orphaned
    paragraph from the block list.

    NOTE: Modifies the ASG dictionary in-place.

    [parameters]
    `node` (Any):: ASG root dictionary or any sub-node to recursively process.
    """
    if not isinstance(node, dict):
        return

    for key in ("blocks", "children", "items"):
        blocks = node.get(key)
        if not isinstance(blocks, list) or not blocks:
            continue

        to_remove: set[int] = set()
        for i, block in enumerate(blocks):
            if i in to_remove or not isinstance(block, dict):
                continue
            if _is_block_title_paragraph(block) and i + 1 < len(blocks):
                next_block = blocks[i + 1]
                if isinstance(next_block, dict) and next_block.get("title") is None:
                    inlines = block.get("inlines", [])
                    if inlines:
                        first = dict(inlines[0])
                        raw = first.get("value", "")
                        if raw.startswith("."):
                            first["value"] = raw[1:]
                        next_block["title"] = [first] + [dict(il) for il in inlines[1:]]
                        to_remove.add(i)

        if to_remove:
            node[key] = [b for j, b in enumerate(blocks) if j not in to_remove]

        for block in node[key]:
            _reattach_block_titles(block)


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
    elif hasattr(node, "title") and node.title:
        res.append(_extract_plain_text(node.title))
    elif hasattr(node, "get_child_collections"):
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
