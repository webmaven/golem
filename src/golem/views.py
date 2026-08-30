"""AsciiDoc derived multi-view compilation engine for Golem.

Provides build-time synthesis of multi-view tabs from AsciiDoc listings:
1. `source`: syntax-highlighted AsciiDoc input (label: "AsciiDoc")
2. `asg`: parsed AST -> ASG JSON -> syntax-highlighted JSON (label: "ASG")
3. `html`: rendered HTML source -> syntax-highlighted HTML (label: "HTML")
4. `preview`: live rendered HTML wrapped in `<div class="rendered-preview">` (label: "Preview")
"""

from __future__ import annotations

import html
import json
import logging
from typing import Any, Callable, Optional, Sequence, Union

import asciidoctrine  # type: ignore[import-untyped]
from asciidoctrine.resolver import ASGResolver  # type: ignore[import-untyped]

from golem.highlighting import make_highlighter

logger = logging.getLogger(__name__)

VIEW_ATTRIBUTES: tuple[str, ...] = ("render", "views", "display", "formats")

CANONICAL_VIEW_MAP: dict[str, str] = {
    "source": "source",
    "asciidoc": "source",
    "adoc": "source",
    "src": "source",
    "asg": "asg",
    "ast": "asg",
    "json": "asg",
    "html": "html",
    "rendered-html": "html",
    "markup": "html",
    "preview": "preview",
    "live": "preview",
    "rendered": "preview",
    "view": "preview",
}

VIEW_LABELS: dict[str, str] = {
    "source": "AsciiDoc",
    "asg": "ASG",
    "html": "HTML",
    "preview": "Preview",
}


def parse_views_attribute(attributes: Optional[dict[str, Any]]) -> list[str]:
    """Extract and normalize requested view identifiers from node attributes.

    Inspects the provided attributes mapping for any of the supported alias keys
    (`render`, `views`, `display`, `formats`). Returns a list of canonical view
    identifiers in the order requested.

    [parameters]
    `attributes` (dict[str, Any] | None):: Node attribute dictionary.

    [returns]
    `list[str]`:: Normalized list of canonical view identifiers (e.g. `["source", "preview"]`).
    """
    if not isinstance(attributes, dict):
        return []

    raw_views: list[str] = []
    for key in VIEW_ATTRIBUTES:
        val = attributes.get(key)
        if val is not None:
            if isinstance(val, str):
                raw_views = [v.strip().lower() for v in val.split(",") if v.strip()]
                break
            if isinstance(val, (list, tuple, set)):
                raw_views = [str(v).strip().lower() for v in val if str(v).strip()]
                break

    canonical_views: list[str] = []
    for v in raw_views:
        c = CANONICAL_VIEW_MAP.get(v, v)
        if c not in canonical_views:
            canonical_views.append(c)

    return canonical_views


def generate_asciidoc_views(
    code_text: str,
    views: Union[str, Sequence[str]],
    highlighter: Optional[Callable[[str, str], Optional[str]]] = None,
) -> list[dict[str, str]]:
    """Synthesize multi-representation derived views for an AsciiDoc snippet.

    Processes an AsciiDoc code listing into multiple derived representations at build time:
    - `source`: syntax-highlighted AsciiDoc input markup.
    - `asg`: parsed AST converted to ASG dictionary, formatted as JSON, and syntax-highlighted.
    - `html`: rendered HTML source markup, syntax-highlighted.
    - `preview`: live rendered HTML wrapped in a `<div class="rendered-preview">` container.

    [parameters]
    `code_text` (str):: Raw AsciiDoc source snippet to compile.
    `views` (str | Sequence[str]):: Comma-separated string or sequence of requested view names.
    `highlighter` (Callable[[str, str], Optional[str]] | None, optional):: Syntax highlighter callable.
        Defaults to `make_highlighter()`.

    [returns]
    `list[dict[str, str]]`:: List of view dictionaries, each containing `id`, `label`, `content`, and `language`.
    """
    if isinstance(views, str):
        raw_list = [v.strip().lower() for v in views.split(",") if v.strip()]
    else:
        raw_list = [str(v).strip().lower() for v in views if str(v).strip()]

    canonical_views: list[str] = []
    for v in raw_list:
        c = CANONICAL_VIEW_MAP.get(v, v)
        if c not in canonical_views:
            canonical_views.append(c)

    if not canonical_views:
        return []

    active_highlighter = highlighter if highlighter is not None else make_highlighter()

    # Cached intermediate representations
    asg_obj: Optional[Any] = None
    asg_dict: Optional[dict[str, Any]] = None
    rendered_html_str: Optional[str] = None

    def _get_asg() -> tuple[Any, dict[str, Any]]:
        nonlocal asg_obj, asg_dict
        if asg_dict is not None and asg_obj is not None:
            return asg_obj, asg_dict
        try:
            ast = asciidoctrine.parse_to_ast(code_text)
            resolver = ASGResolver(ast)
            asg_obj = resolver.resolve(ast)
            if hasattr(asg_obj, "to_dict"):
                asg_dict = asg_obj.to_dict()
            elif isinstance(asg_obj, dict):
                asg_dict = asg_obj
            else:
                asg_dict = {"name": "document", "blocks": []}
        except Exception as err:
            logger.warning("Failed to parse AsciiDoc snippet into ASG: %s", err)
            asg_dict = {"error": str(err)}
            asg_obj = asg_dict
        return asg_obj, asg_dict

    def _get_rendered_html() -> str:
        nonlocal rendered_html_str
        if rendered_html_str is not None:
            return rendered_html_str
        resolved_asg, _ = _get_asg()
        try:
            from golem.renderer import render_body

            rendered_html_str = render_body(resolved_asg, highlighter=active_highlighter)
        except Exception as err:
            logger.warning("Failed to render ASG to HTML: %s", err)
            rendered_html_str = f'<div class="error">{html.escape(str(err))}</div>'
        return rendered_html_str

    result: list[dict[str, str]] = []

    for view_id in canonical_views:
        label = VIEW_LABELS.get(view_id, view_id.capitalize())

        if view_id == "source":
            highlighted = active_highlighter(code_text, "asciidoc")
            if not highlighted:
                highlighted = (
                    f'<pre class="highlight asciidoc"><code class="language-asciidoc">{html.escape(code_text)}</code></pre>'
                )
            result.append(
                {
                    "id": "source",
                    "label": label,
                    "content": highlighted,
                    "language": "asciidoc",
                }
            )

        elif view_id == "asg":
            _, data_dict = _get_asg()
            json_str = json.dumps(data_dict, indent=2, default=str)
            highlighted_json = active_highlighter(json_str, "json")
            if not highlighted_json:
                highlighted_json = (
                    f'<pre class="highlight json"><code class="language-json">{html.escape(json_str)}</code></pre>'
                )
            result.append(
                {
                    "id": "asg",
                    "label": label,
                    "content": highlighted_json,
                    "language": "json",
                }
            )

        elif view_id == "html":
            rendered_html = _get_rendered_html()
            highlighted_html = active_highlighter(rendered_html.strip(), "html")
            if not highlighted_html:
                highlighted_html = (
                    f'<pre class="highlight html"><code class="language-html">{html.escape(rendered_html)}</code></pre>'
                )
            result.append(
                {
                    "id": "html",
                    "label": label,
                    "content": highlighted_html,
                    "language": "html",
                }
            )

        elif view_id == "preview":
            rendered_html = _get_rendered_html()
            preview_content = f'<div class="rendered-preview">\n{rendered_html}\n</div>'
            result.append(
                {
                    "id": "preview",
                    "label": label,
                    "content": preview_content,
                    "language": "preview",
                }
            )

    return result


def extract_listing_views(
    node: dict[str, Any],
    highlighter: Optional[Callable[[str, str], Optional[str]]] = None,
) -> list[dict[str, str]]:
    """Extract requested derived views from an ASG listing block node.

    [parameters]
    `node` (dict[str, Any]):: ASG listing node dictionary.
    `highlighter` (Callable[[str, str], Optional[str]] | None, optional):: Syntax highlighter callable.

    [returns]
    `list[dict[str, str]]`:: List of derived view representations, or an empty list if no views were requested.
    """
    if not isinstance(node, dict):
        return []

    attributes = node.get("attributes")
    if not isinstance(attributes, dict):
        return []

    views = parse_views_attribute(attributes)
    if not views:
        return []

    code_text = node.get("value")
    if code_text is None:
        inlines = node.get("inlines", [])
        if inlines:
            from golem.renderer import _extract_plain_text

            code_text = _extract_plain_text(inlines)
        else:
            code_text = ""

    return generate_asciidoc_views(
        code_text=str(code_text),
        views=views,
        highlighter=highlighter,
    )
