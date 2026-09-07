"""Protocols and shared utilities for Golem multi-view rendering pipeline."""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, Union, runtime_checkable


@runtime_checkable
class BodyRendererProtocol(Protocol):
    """Protocol specifying the interface for rendering body HTML from ASG nodes.

    Implementations accept an ASG dictionary or AST Node and render it into
    an HTML5 body fragment string.
    """

    def __call__(
        self,
        asg_root: Any,
        search_paths: Any = None,
        highlighter: Optional[Callable[[str, str], Optional[str]]] = None,
    ) -> str:
        """Render an ASG node or AST structure into HTML markup.

        [parameters]
        `asg_root` (Any):: AST Node or ASG dictionary representation of document or fragment.
        `search_paths` (Any, optional):: Optional directory paths containing template overrides. Defaults to `None`.
        `highlighter` (Callable[[str, str], Optional[str]] | None, optional):: Syntax highlighter callable. Defaults to `None`.

        [returns]
        `str`:: Rendered HTML5 body markup.
        """
        ...


_default_renderer: Optional[Union[BodyRendererProtocol, Callable[..., str]]] = None


def set_default_renderer(
    renderer: Union[BodyRendererProtocol, Callable[..., str]],
) -> None:
    """Register the default body renderer callable for views synthesis.

    [parameters]
    `renderer` (BodyRendererProtocol | Callable[..., str]):: Body renderer callable or protocol implementation.
    """
    global _default_renderer
    _default_renderer = renderer


def get_default_renderer() -> Optional[Union[BodyRendererProtocol, Callable[..., str]]]:
    """Retrieve the currently registered default body renderer callable.

    [returns]
    `BodyRendererProtocol | Callable[..., str] | None`:: Registered default renderer, or `None` if unconfigured.
    """
    return _default_renderer


def extract_plain_text(node: Any) -> str:
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
        return "".join(extract_plain_text(item) for item in node)
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
                res.append(extract_plain_text(node[key]))
        return "".join(res)
    if hasattr(node, "value") and node.value is not None:
        return str(node.value)
    if hasattr(node, "text") and node.text is not None:
        return str(node.text)
    res = []
    if hasattr(node, "inlines") and node.inlines:
        res.append(extract_plain_text(node.inlines))
    elif hasattr(node, "title") and node.title:
        res.append(extract_plain_text(node.title))
    elif hasattr(node, "get_child_collections"):
        for collection in node.get_child_collections().values():
            for child in collection:
                res.append(extract_plain_text(child))
    elif hasattr(node, "children") and node.children:
        for child in node.children:
            res.append(extract_plain_text(child))
    return "".join(res)


_extract_plain_text = extract_plain_text
