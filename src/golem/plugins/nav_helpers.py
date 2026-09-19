"""Provide breadcrumbs navigation, flattened navigation trees, and template context helpers.

== Overview

`NavigationHelpersPlugin` inspects the hierarchical site navigation structure
and active document context to enrich Chameleon template renderings with:
- `breadcrumbs`: Ordered ancestor list from site root ("Home") to the current page.
- `nav_tree_flat`: Ordered depth-first sequence of all navigation items with depth metadata.
- Preservation of precomputed engine pagination (`prev_page`, `next_page`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from golem.metadata import clean_index_url, title_from_filename
from golem.plugins import GolemPlugin, hookimpl

__all__ = [
    "NavigationHelpersPlugin",
]


def _get(entry: Any, key: str, default: Any = None) -> Any:
    """Retrieve an attribute or dictionary key from a navigation entry.

    [parameters]
    `entry` (Any):: Navigation entry object or dictionary.
    `key` (str):: Attribute or dictionary key name to retrieve.
    `default` (Any, optional):: Fallback value if key is not found. Defaults to `None`.

    [returns]
    `Any`:: Retrieved value or fallback default.
    """
    if isinstance(entry, dict):
        return entry.get(key, default)
    val = getattr(entry, key, None)
    if val is not None:
        return val
    if hasattr(entry, "__getitem__"):
        try:
            return entry[key]
        except (KeyError, TypeError, IndexError):
            pass
    return default


def _matches(node: Any, current_path_str: str | None, doc_path: Path) -> bool:
    """Determine if a navigation node corresponds to the current page.

    [parameters]
    `node` (Any):: Navigation tree node dictionary or object.
    `current_path_str` (str | None):: Current relative document path from context.
    `doc_path` (Path):: File path of the document being compiled.

    [returns]
    `bool`:: `True` if node matches the current page, `False` otherwise.
    """
    node_path = _get(node, "path")
    node_url = _get(node, "url")

    targets: set[str] = set()
    if current_path_str:
        cp = Path(current_path_str).as_posix()
        targets.add(cp)
        cp_html = Path(cp).with_suffix(".html").as_posix()
        targets.add(cp_html)
        targets.add(clean_index_url(cp_html))

    if doc_path:
        dp_name = doc_path.name
        targets.add(dp_name)
        dp_html = doc_path.with_suffix(".html").name
        targets.add(dp_html)
        targets.add(clean_index_url(dp_html))
        targets.add(doc_path.as_posix())

    if node_path is not None:
        np_posix = Path(str(node_path)).as_posix()
        if np_posix in targets:
            return True
        if "/" not in np_posix and np_posix in targets:
            return True

    if node_url is not None:
        nu = str(node_url)
        if nu in targets or nu.lstrip("./") in targets:
            return True

    return False


def _find_chain(nodes: list[Any], current_path_str: str | None, doc_path: Path) -> list[Any] | None:
    """Iteratively traverse navigation nodes to find the ancestor chain to current page.

    [parameters]
    `nodes` (list[Any]):: List of navigation tree nodes.
    `current_path_str` (str | None):: Current relative document path from context.
    `doc_path` (Path):: File path of the document being compiled.

    [returns]
    `list[Any] | None`:: Ordered chain of nodes from top level to current page, or `None` if not found.
    """
    if not nodes:
        return None

    stack: list[tuple[Any, int]] = [(node, 0) for node in reversed(nodes)]
    active_chain: list[Any] = []

    while stack:
        node, depth = stack.pop()
        active_chain[depth:] = [node]

        if _matches(node, current_path_str, doc_path):
            return list(active_chain)

        children = _get(node, "children", []) or []
        if children:
            for child in reversed(children):
                stack.append((child, depth + 1))

    return None


def _flatten_nav_tree(nodes: list[Any], current_depth: int = 0) -> list[dict[str, Any]]:
    """Flatten a hierarchical navigation tree in depth-first order.

    [parameters]
    `nodes` (list[Any]):: List of hierarchical navigation tree nodes.
    `current_depth` (int, optional):: Current nesting depth level. Defaults to `0`.

    [returns]
    `list[dict[str, Any]]`:: Flattened ordered list of navigation entries with depth.
    """
    flat: list[dict[str, Any]] = []
    for node in nodes:
        title = _get(node, "title", "")
        url = _get(node, "url", "")
        flat.append(
            {
                "title": str(title),
                "url": str(url),
                "depth": current_depth,
            }
        )
        children = _get(node, "children", []) or []
        if children:
            flat.extend(_flatten_nav_tree(children, current_depth=current_depth + 1))
    return flat


def _is_home_page(current_path_str: str | None, doc_path: Path, home_title: str, title: str | None) -> bool:
    """Determine if the document being compiled represents the site home page.

    [parameters]
    `current_path_str` (str | None):: Relative document path from context.
    `doc_path` (Path):: File path of the document being compiled.
    `home_title` (str):: Configured title of the home page.
    `title` (str | None):: Page title from context.

    [returns]
    `bool`:: `True` if document is the root home page, `False` otherwise.
    """
    if current_path_str is not None:
        cp = Path(current_path_str).as_posix()
        if cp in ("", ".", "index.adoc", "index.html", "README.adoc", "./index.html"):
            return True
        if "/" in cp:
            return False
    if doc_path.name in ("index.adoc", "index.html", "README.adoc"):
        if current_path_str is None or "/" not in str(current_path_str):
            return True
    if title and title.strip().lower() == home_title.strip().lower():
        if current_path_str is None or "/" not in str(current_path_str):
            return True
    return False


def _is_home_node(node: Any, home_title: str, home_url: str) -> bool:
    """Determine if a navigation node corresponds to the home page.

    [parameters]
    `node` (Any):: Navigation tree node dictionary or object.
    `home_title` (str):: Configured title of the home page.
    `home_url` (str):: Resolved URL of the home page.

    [returns]
    `bool`:: `True` if node represents the home page, `False` otherwise.
    """
    title = str(_get(node, "title", ""))
    url = str(_get(node, "url", ""))
    path = str(_get(node, "path", ""))
    if title.strip().lower() == home_title.strip().lower():
        return True
    if url in (home_url, "/", "./", "index.html"):
        return True
    if path in ("index.adoc", "index.html", "README.adoc"):
        return True
    return False


class NavigationHelpersPlugin(GolemPlugin):
    """Provide breadcrumbs navigation, flattened nav tree, and context helpers.

    [attributes]
    `home_title` (str):: Display title for the root home breadcrumb. Defaults to `"Home"`.
    `home_url` (str | None):: Target URL for the root home breadcrumb. Defaults to context root_path or `"/"`.

    === Examples

    [source,python]
    ----
    from golem.plugins.nav_helpers import NavigationHelpersPlugin

    plugin = NavigationHelpersPlugin(home_title="Home")
    ----
    """

    name = "nav_helpers"

    def __init__(self, home_title: str = "Home", home_url: str | None = None, **extra: Any) -> None:
        """Initialize navigation helpers plugin with home breadcrumb configuration.

        [parameters]
        `home_title` (str, optional):: Label for the site root breadcrumb entry. Defaults to `"Home"`.
        `home_url` (str | None, optional):: Link URL for the root breadcrumb entry. Defaults to `None`.
        `**extra`:: Additional plugin configuration options.
        """
        super().__init__(home_title=home_title, home_url=home_url, **extra)
        self.home_title = home_title
        self.home_url = home_url

    @classmethod
    def from_config(cls, config: Any = None) -> NavigationHelpersPlugin:
        """Instantiate NavigationHelpersPlugin from site configuration or dictionary.

        [parameters]
        `config` (Any, optional):: Site configuration object or dictionary. Defaults to `None`.

        [returns]
        `NavigationHelpersPlugin`:: Configured plugin instance.
        """
        if config is None:
            return cls()

        plugin_configs = getattr(config, "plugin_configs", {}) or {}
        nav_cfg = plugin_configs.get("nav_helpers", {}) if isinstance(plugin_configs, dict) else {}
        if isinstance(config, dict):
            nav_cfg = config.get("nav_helpers", config)

        home_title = getattr(config, "home_title", None) or (
            nav_cfg.get("home_title", "Home") if isinstance(nav_cfg, dict) else "Home"
        )
        home_url = getattr(config, "home_url", None) or (nav_cfg.get("home_url", None) if isinstance(nav_cfg, dict) else None)
        return cls(home_title=home_title, home_url=home_url)

    @hookimpl
    def on_template_context(self, context: dict[str, Any], doc_path: Path) -> dict[str, Any]:
        """Intercept and enrich template context with breadcrumbs and flattened nav tree.

        [parameters]
        `context` (dict[str, Any]):: Chameleon template context dictionary.
        `doc_path` (Path):: Path to the documentation source file being processed.

        [returns]
        `dict[str, Any]`:: Enriched template context containing breadcrumbs and nav_tree_flat.
        """
        current_path = context.get("current_path")
        current_path_str = str(current_path) if current_path is not None else None
        page_title = context.get("title")

        # Resolve home_url: defaults to root_path in context if present and truthy, otherwise "/"
        if self.home_url is not None:
            resolved_home_url = self.home_url
        elif context.get("root_path"):
            resolved_home_url = context["root_path"]
        else:
            resolved_home_url = "/"

        nav_tree = context.get("nav_tree") or []
        nav_tree_flat = _flatten_nav_tree(nav_tree)

        # Build breadcrumbs
        breadcrumbs: list[dict[str, Any]] = []
        is_home = _is_home_page(current_path_str, doc_path, self.home_title, page_title)

        if not nav_tree:
            if is_home:
                breadcrumbs.append(
                    {
                        "title": self.home_title,
                        "url": resolved_home_url,
                        "is_current": True,
                    }
                )
            else:
                breadcrumbs.append(
                    {
                        "title": self.home_title,
                        "url": resolved_home_url,
                        "is_current": False,
                    }
                )
                doc_title = page_title or title_from_filename(doc_path.name)
                doc_url = context.get("url") or (
                    clean_index_url(Path(current_path_str).with_suffix(".html").as_posix())
                    if current_path_str
                    else clean_index_url(doc_path.with_suffix(".html").name)
                )
                breadcrumbs.append(
                    {
                        "title": doc_title,
                        "url": doc_url,
                        "is_current": True,
                    }
                )
        else:
            chain = _find_chain(nav_tree, current_path_str, doc_path)
            if chain is None:
                if is_home:
                    breadcrumbs.append(
                        {
                            "title": self.home_title,
                            "url": resolved_home_url,
                            "is_current": True,
                        }
                    )
                else:
                    breadcrumbs.append(
                        {
                            "title": self.home_title,
                            "url": resolved_home_url,
                            "is_current": False,
                        }
                    )
                    doc_title = page_title or title_from_filename(doc_path.name)
                    doc_url = context.get("url") or (
                        clean_index_url(Path(current_path_str).with_suffix(".html").as_posix())
                        if current_path_str
                        else clean_index_url(doc_path.with_suffix(".html").name)
                    )
                    breadcrumbs.append(
                        {
                            "title": doc_title,
                            "url": doc_url,
                            "is_current": True,
                        }
                    )
            else:
                # Chain found in nav_tree
                # Check if matched node itself is Home
                if len(chain) == 1 and _is_home_node(chain[0], self.home_title, resolved_home_url):
                    breadcrumbs.append(
                        {
                            "title": _get(chain[0], "title", self.home_title),
                            "url": resolved_home_url,
                            "is_current": True,
                        }
                    )
                else:
                    # Prepend home entry if chain does not start with home
                    first_node = chain[0]
                    if _is_home_node(first_node, self.home_title, resolved_home_url):
                        # Chain already starts with home
                        breadcrumbs.append(
                            {
                                "title": _get(first_node, "title", self.home_title),
                                "url": resolved_home_url,
                                "is_current": False,
                            }
                        )
                        chain_rest = chain[1:]
                    else:
                        breadcrumbs.append(
                            {
                                "title": self.home_title,
                                "url": resolved_home_url,
                                "is_current": False,
                            }
                        )
                        chain_rest = chain

                    for idx, node in enumerate(chain_rest):
                        is_last = idx == len(chain_rest) - 1
                        breadcrumbs.append(
                            {
                                "title": str(_get(node, "title", "")),
                                "url": str(_get(node, "url", "")),
                                "is_current": is_last,
                            }
                        )

        injected: dict[str, Any] = {
            "breadcrumbs": breadcrumbs,
            "nav_tree_flat": nav_tree_flat,
        }
        # Do not overwrite prev_page / next_page if already present
        context.update(injected)
        return context
