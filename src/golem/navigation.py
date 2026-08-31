"""Provide hierarchical navigation tree discovery, semantic HTML menu generation, and pagination.

== Navigation Architecture

Golem automatically discovers navigation structure by recursively scanning the content directory.
The navigation tree respects:
- Explicit ordering specified via `config.navigation_nav` in `golem.toml`.
- Index documents (`index.adoc`, `README.adoc`) pinned to the top of directories.
- Numerical or custom sorting orders specified via `:nav_order:` document attributes.
- Natural alphanumeric ordering with automatic cleanup of numeric prefixes (e.g. `01-intro.adoc` -> `Intro`).
- Exclusion of underscore-prefixed partials (e.g. `_sidebar.adoc`) and hidden files/directories.
- Automatic pruning of empty directories and directories lacking valid `.adoc` content.

== Semantic HTML Navigation and Pagination

The discovered navigation tree is rendered into accessible, semantic HTML (`<nav class="golem-nav">`)
with active state highlighting (`aria-current="page"` and `class="active"`) based on the currently
compiled document's relative path. Linear document pagination (previous/next links) is computed
via depth-first traversal of the navigation tree.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from golem.metadata import (
    clean_index_url,
    dir_has_adoc_content,
    title_from_filename,
)

__all__ = [
    "NavigationBuilder",
]


class NavigationBuilder:
    """Hierarchical site navigation builder, HTML renderer, and pagination generator.

    Discovers published documents across the content directory, constructs nested navigation
    trees, renders semantic navigation menus with active states, and computes sequential
    previous/next reading pagination.

    [attributes]
    `config` (Any):: Resolved site configuration or GolemConfig instance.
    `content_dir` (Path):: Absolute path to the source content directory.
    `is_partial` (Callable[[Path], bool]):: Predicate function determining if a file or directory is a partial.
    `get_file_metadata` (Callable[[Path], dict[str, Any]]):: Function retrieving cached or parsed document metadata.

    === Examples

    [source,python]
    ----
    from pathlib import Path
    from golem.config import GolemConfig
    from golem.navigation import NavigationBuilder

    config = GolemConfig(content_dir="content", output_dir="dist")
    builder = NavigationBuilder(config, Path("content"), lambda p: p.name.startswith("_"), lambda p: {})
    nav_tree = builder.discover_navigation()
    ----
    """

    def __init__(
        self,
        config: Any,
        content_dir: Path,
        is_partial_fn: Callable[[Path], bool],
        get_metadata_fn: Callable[[Path], dict[str, Any]],
    ) -> None:
        """Initialize the navigation builder with directory paths and metadata helpers.

        [parameters]
        `config` (Any):: Resolved site configuration or GolemConfig instance.
        `content_dir` (Path):: Source content directory path.
        `is_partial_fn` (Callable[[Path], bool]):: Callable returning `True` if a path represents a partial.
        `get_metadata_fn` (Callable[[Path], dict[str, Any]]):: Callable retrieving document metadata for a given path.
        """
        self.config = config
        self.content_dir = Path(content_dir).resolve()
        self.is_partial = is_partial_fn
        self.get_file_metadata = get_metadata_fn

    def discover_navigation(self) -> list[dict[str, Any]]:
        """Discover and assemble the hierarchical site navigation tree from content files.

        Recursively scans `content_dir` for publishable `.adoc` documents (excluding
        partial files starting with `_` and hidden files starting with `.`). Supports
        explicit ordering via `config.navigation_nav`, pins directory index documents
        (`index.adoc`, `README.adoc`) at the top of sections, respects `:nav_order:`
        attributes, and strips sorting prefixes from display titles.

        [returns]
        `list[dict[str, Any]]`:: Hierarchical list of navigation item dictionaries containing `"title"`, `"path"`, `"url"`, and `"children"`.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.config import GolemConfig
        from golem.navigation import NavigationBuilder

        config = GolemConfig(content_dir="content", output_dir="dist")
        builder = NavigationBuilder(config, Path("content"), lambda p: False, lambda p: {})
        nav_tree = builder.discover_navigation()
        ----
        """
        # If navigation_nav is explicitly configured, use it as manual override order
        if getattr(self.config, "navigation_nav", None) is not None and len(self.config.navigation_nav) > 0:
            nav_items: list[dict[str, Any]] = []
            for item in self.config.navigation_nav:
                p = self.content_dir / item
                if self.is_partial(p):
                    continue
                meta = (
                    self.get_file_metadata(p)
                    if p.exists()
                    else {
                        "title": title_from_filename(item),
                        "nav_title": title_from_filename(item),
                    }
                )
                title = meta.get("nav_title") or meta.get("title", title_from_filename(item))
                rel_url = clean_index_url(Path(item).with_suffix(".html").as_posix())
                nav_items.append(
                    {
                        "title": title,
                        "path": item,
                        "url": rel_url,
                        "children": [],
                    }
                )
            return nav_items

        if not self.content_dir.exists():
            return []

        def build_tree(current_dir: Path) -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            if not current_dir.exists():
                return items

            try:
                entries = list(current_dir.iterdir())
            except Exception:
                return items

            valid_entries = [e for e in entries if not e.name.startswith(".") and not e.name.startswith("_")]

            files = [e for e in valid_entries if e.is_file() and e.suffix == ".adoc"]
            dirs = [e for e in valid_entries if e.is_dir()]

            def _file_sort_key(p: Path) -> tuple[int, str]:
                meta = self.get_file_metadata(p)
                order = meta.get("nav_order")
                return (order if order is not None else 999, p.name.lower())

            def _dir_sort_key(d: Path) -> tuple[int, str]:
                sub_index: Path | None = None
                try:
                    # Prefer index.adoc first, then readme.adoc
                    for target_stem in ("index", "readme"):
                        for sub_f in d.iterdir():
                            if sub_f.is_file() and sub_f.suffix == ".adoc" and sub_f.stem.lower() == target_stem:
                                sub_index = sub_f
                                break
                        if sub_index is not None:
                            break
                except Exception:
                    pass
                if sub_index is not None:
                    meta = self.get_file_metadata(sub_index)
                    order = meta.get("nav_order")
                    if order is not None:
                        return (order, d.name.lower())
                return (999, d.name.lower())

            files.sort(key=_file_sort_key)
            dirs.sort(key=_dir_sort_key)

            index_file: Path | None = None
            for target_stem in ("index", "readme"):
                for f in files:
                    if f.stem.lower() == target_stem:
                        index_file = f
                        break
                if index_file is not None:
                    break

            if current_dir == self.content_dir and index_file is not None:
                rel_p = index_file.relative_to(self.content_dir).as_posix()
                rel_u = clean_index_url(index_file.relative_to(self.content_dir).with_suffix(".html").as_posix())
                meta = self.get_file_metadata(index_file)
                title = meta.get("nav_title") or meta.get("title", "")
                items.append(
                    {
                        "title": title,
                        "path": rel_p,
                        "url": rel_u,
                        "children": [],
                    }
                )

            for f in files:
                if current_dir == self.content_dir and f == index_file:
                    continue
                if current_dir != self.content_dir and f == index_file:
                    continue
                rel_p = f.relative_to(self.content_dir).as_posix()
                rel_u = clean_index_url(f.relative_to(self.content_dir).with_suffix(".html").as_posix())
                meta = self.get_file_metadata(f)
                title = meta.get("nav_title") or meta.get("title", "")
                items.append(
                    {
                        "title": title,
                        "path": rel_p,
                        "url": rel_u,
                        "children": [],
                    }
                )

            for d in dirs:
                if not dir_has_adoc_content(d):
                    continue
                sub_index = None
                try:
                    for target_stem in ("index", "readme"):
                        for sub_f in d.iterdir():
                            if sub_f.is_file() and sub_f.suffix == ".adoc" and sub_f.stem.lower() == target_stem:
                                sub_index = sub_f
                                break
                        if sub_index is not None:
                            break
                except Exception:
                    pass

                sub_children = build_tree(d)

                if sub_index is not None:
                    meta = self.get_file_metadata(sub_index)
                    sec_title = meta.get("nav_title") or meta.get("title", "")
                    sec_url = clean_index_url(sub_index.relative_to(self.content_dir).with_suffix(".html").as_posix())
                    sec_path = sub_index.relative_to(self.content_dir).as_posix()
                else:
                    sec_title = title_from_filename(d.name)
                    sec_url = None
                    sec_path = d.relative_to(self.content_dir).as_posix()

                items.append(
                    {
                        "title": sec_title,
                        "path": sec_path,
                        "url": sec_url,
                        "children": sub_children,
                    }
                )

            return items

        return build_tree(self.content_dir)

    def generate_nav_html(
        self,
        current_rel_path: Path | None = None,
        nav_tree: list[dict[str, Any]] | None = None,
    ) -> str:
        """Render the hierarchical site navigation tree into semantic HTML with contextual active states.

        Converts the navigation tree from `discover_navigation()` into nested `<ul class="golem-nav-list">`
        and `<ul class="golem-nav-sublist">` HTML elements wrapped within a `<nav class="golem-nav">`
        container. Calculates relative path prefixes (`../` segments) based on `current_rel_path`
        and marks the active page with `aria-current="page"` and `class="active"`.

        [parameters]
        `current_rel_path` (Path | None, optional):: Path of the currently compiling document relative to `content_dir`, used to compute relative URL depth and highlight active items. Defaults to `None`.
        `nav_tree` (list[dict[str, Any]] | None, optional):: Pre-computed navigation tree. If `None`, calls `discover_navigation()`. Defaults to `None`.

        [returns]
        `str`:: Rendered semantic HTML string for the navigation menu, or empty string `""` if navigation is empty.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.config import GolemConfig
        from golem.navigation import NavigationBuilder

        config = GolemConfig(content_dir="content", output_dir="dist")
        builder = NavigationBuilder(config, Path("content"), lambda p: False, lambda p: {})
        nav_html = builder.generate_nav_html(current_rel_path=Path("guides/intro.adoc"))
        assert '<nav class="golem-nav">' in nav_html
        ----
        """
        resolved_tree = nav_tree if nav_tree is not None else self.discover_navigation()
        if not resolved_tree:
            return ""

        prefix = ""
        if current_rel_path is not None:
            depth = len(current_rel_path.parent.parts)
            if depth > 0:
                prefix = "../" * depth

        curr_posix = current_rel_path.as_posix() if current_rel_path else None
        curr_html = current_rel_path.with_suffix(".html").as_posix() if current_rel_path else None

        def render_list(items: list[dict[str, Any]], is_nested: bool = False) -> list[str]:
            ul_class = "golem-nav-sublist" if is_nested else "golem-nav-list"
            out = [f'<ul class="{ul_class}">\n']
            for item in items:
                title = item.get("title", "")
                url = item.get("url")
                item_path = item.get("path")
                children = item.get("children", [])
                href = f"{prefix}{url}" if url else None
                # Collapse redundant './' segment: '.././' -> '../', '../.././' -> '../../'
                if href and href.endswith("./") and len(href) > 2:
                    href = href[:-2]
                is_current = bool((curr_posix and item_path == curr_posix) or (curr_html and url == curr_html))

                if children:
                    sec_class = "golem-nav-section active" if is_current else "golem-nav-section"
                    out.append(f'  <li class="{sec_class}">\n')
                    curr_attr = ' aria-current="page" class="active"' if is_current else ""
                    if href:
                        out.append(
                            f'    <span class="golem-nav-section-title"><a href="{href}"{curr_attr}>{title}</a></span>\n'
                        )
                    else:
                        out.append(f'    <span class="golem-nav-section-title">{title}</span>\n')
                    out.extend(render_list(children, is_nested=True))
                    out.append("  </li>\n")
                else:
                    item_class = "golem-nav-item active" if is_current else "golem-nav-item"
                    curr_attr = ' aria-current="page" class="active"' if is_current else ""
                    out.append(f'  <li class="{item_class}">')
                    if href:
                        out.append(f'<a href="{href}"{curr_attr}>{title}</a>')
                    else:
                        out.append(f"<span>{title}</span>")
                    out.append("</li>\n")
            out.append("</ul>\n")
            return out

        res = ['<nav class="golem-nav">\n']
        res.extend(render_list(resolved_tree, is_nested=False))
        res.append("</nav>")
        return "".join(res)

    def get_ordered_nav_pages(
        self,
        nav_tree: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Flatten the hierarchical site navigation tree into a linear sequence of pages.

        Performs a depth-first traversal of `discover_navigation()` to produce an ordered
        linear sequence of navigable document entries. Used by `get_page_pagination()` to
        calculate previous and next sequential reading links.

        [parameters]
        `nav_tree` (list[dict[str, Any]] | None, optional):: Pre-computed navigation tree. If `None`, calls `discover_navigation()`. Defaults to `None`.

        [returns]
        `list[dict[str, Any]]`:: Linear list of page dictionaries containing `"title"`, `"url"`, and `"path"`.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.config import GolemConfig
        from golem.navigation import NavigationBuilder

        config = GolemConfig(content_dir="content", output_dir="dist")
        builder = NavigationBuilder(config, Path("content"), lambda p: False, lambda p: {})
        pages = builder.get_ordered_nav_pages()
        ----
        """
        resolved_tree = nav_tree if nav_tree is not None else self.discover_navigation()
        pages: list[dict[str, Any]] = []

        def _flatten(items: list[dict[str, Any]]) -> None:
            for item in items:
                title = item.get("title", "")
                url = item.get("url")
                path = item.get("path")
                children = item.get("children", [])

                if url:
                    pages.append({"title": title, "url": url, "path": path or ""})
                if children:
                    _flatten(children)

        _flatten(resolved_tree)
        return pages

    def get_page_pagination(
        self,
        current_rel_path: Path | None = None,
        nav_tree: list[dict[str, Any]] | None = None,
    ) -> tuple[dict[str, str] | None, dict[str, str] | None]:
        """Calculate previous and next sequential pagination links for a given document.

        Locates `current_rel_path` within the linear sequence produced by `get_ordered_nav_pages()`
        and determines the immediately preceding and following document links, adjusting
        relative URL prefixes (`../` segments) according to the directory depth of `current_rel_path`.

        [parameters]
        `current_rel_path` (Path | None, optional):: Relative path of the active document within `content_dir`. Defaults to `None`.
        `nav_tree` (list[dict[str, Any]] | None, optional):: Pre-computed navigation tree. If `None`, calls `get_ordered_nav_pages()` which discovers navigation. Defaults to `None`.

        [returns]
        `tuple[dict[str, str] | None, dict[str, str] | None]`:: A 2-tuple `(prev_page, next_page)`. Each element is either a dictionary containing `"title"`, `"url"`, and `"path"`, or `None` if at the start/end of the sequence.

        === Examples

        [source,python]
        ----
        from pathlib import Path
        from golem.config import GolemConfig
        from golem.navigation import NavigationBuilder

        config = GolemConfig(content_dir="content", output_dir="dist")
        builder = NavigationBuilder(config, Path("content"), lambda p: False, lambda p: {})
        prev_p, next_p = builder.get_page_pagination(current_rel_path=Path("02-guide.adoc"))
        ----
        """
        if current_rel_path is None:
            return None, None

        pages = self.get_ordered_nav_pages(nav_tree=nav_tree)
        if not pages:
            return None, None

        depth = len(current_rel_path.parent.parts)
        prefix = ("../" * depth) if depth > 0 else ""

        curr_posix = current_rel_path.as_posix()
        curr_html = current_rel_path.with_suffix(".html").as_posix()

        curr_idx = -1
        for idx, p in enumerate(pages):
            if p["path"] == curr_posix or p["url"] == curr_html or p["url"] == clean_index_url(curr_html):
                curr_idx = idx
                break

        if curr_idx == -1:
            return None, None

        prev_item: dict[str, str] | None = None
        if curr_idx > 0:
            raw_prev = pages[curr_idx - 1]
            prev_url = f"{prefix}{raw_prev['url']}"
            if prev_url.endswith("./") and len(prev_url) > 2:
                prev_url = prev_url[:-2]
            prev_item = {
                "title": raw_prev["title"],
                "url": prev_url,
                "path": raw_prev["path"],
            }

        next_item: dict[str, str] | None = None
        if curr_idx < len(pages) - 1:
            raw_next = pages[curr_idx + 1]
            next_url = f"{prefix}{raw_next['url']}"
            if next_url.endswith("./") and len(next_url) > 2:
                next_url = next_url[:-2]
            next_item = {
                "title": raw_next["title"],
                "url": next_url,
                "path": raw_next["path"],
            }

        return prev_item, next_item
