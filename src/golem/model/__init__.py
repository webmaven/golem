"""golem.model — public API for typed ASG traversal and template context contracts.

Re-exports asciidoctrine's visitor/transformer infrastructure under
Golem-stable names so plugins can subclass without importing asciidoctrine
internals directly. Also formalizes TemplateContext, PageContext, and plugin
context contribution contracts as TypedDict models.
"""

from __future__ import annotations

from typing import Any, TypedDict

from asciidoctrine.nodes import (
    Node,
    NodeTransformer as AsgTransformer,
    NodeVisitor as AsgVisitor,
)

__all__ = [
    "AsgTransformer",
    "AsgVisitor",
    "BreadcrumbItem",
    "GlossaryContext",
    "GlossaryContribution",
    "GlossaryEntry",
    "IndexContext",
    "IndexContribution",
    "IndexTermEntry",
    "NavFlatItem",
    "NavHelpersContext",
    "NavHelpersContribution",
    "NavItem",
    "NavTreeItem",
    "Node",
    "PageContext",
    "PageLink",
    "SourceLinksContext",
    "SourceLinksContribution",
    "TemplateContext",
]


class NavTreeItem(TypedDict, total=False):
    """Hierarchical navigation tree item.

    [attributes]
    `title` (str):: Navigation node display label.
    `url` (str):: Target link URL.
    `path` (str):: Source document path.
    `children` (list[NavTreeItem]):: Nested sub-navigation items.
    """

    title: str
    url: str
    path: str
    children: list[NavTreeItem]


NavItem = NavTreeItem


class PageLink(TypedDict, total=False):
    """Sequential pagination navigation link.

    [attributes]
    `title` (str):: Target page title.
    `url` (str):: Target page link URL.
    """

    title: str
    url: str


class BreadcrumbItem(TypedDict, total=False):
    """Hierarchical ancestor breadcrumb entry.

    [attributes]
    `title` (str):: Breadcrumb display label.
    `url` (str):: Target page URL.
    `is_current` (bool):: True if this item represents the active page.
    """

    title: str
    url: str
    is_current: bool


class NavFlatItem(TypedDict, total=False):
    """Flattened navigation tree item with depth metadata.

    [attributes]
    `title` (str):: Navigation item label.
    `url` (str):: Navigation link URL.
    `depth` (int):: Tree nesting depth level.
    """

    title: str
    url: str
    depth: int


class GlossaryEntry(TypedDict, total=False):
    """Alphabetized glossary definition entry.

    [attributes]
    `term` (str):: Defined glossary term.
    `definition` (str):: Term definition text.
    `doc_path` (str):: Origin document path.
    """

    term: str
    definition: str
    doc_path: str


class IndexTermEntry(TypedDict, total=False):
    """Alphabetized hierarchical index term entry.

    [attributes]
    `locations` (list[str]):: Source document paths referencing this term.
    `secondary` (dict[str, Any]):: Secondary subterm entries.
    `subterms` (dict[str, Any]):: Alias mapping for secondary subterms.
    """

    locations: list[str]
    secondary: dict[str, Any]
    subterms: dict[str, Any]


class SourceLinksContext(TypedDict, total=False):
    """Template context contributions from the source_links plugin.

    [attributes]
    `source_repo_url` (str | None):: Canonical web URL to the source repository.
    `source_edit_url` (str | None):: Canonical web URL to edit source file in git host.
    `source_view_url` (str | None):: Canonical web URL to view raw source file.
    `source_url` (str | None):: Canonical web URL to view raw source file.
    `source_provider` (str | None):: Hosting provider identifier.
    """

    source_repo_url: str | None
    source_edit_url: str | None
    source_view_url: str | None
    source_url: str | None
    source_provider: str | None


SourceLinksContribution = SourceLinksContext


class NavHelpersContext(TypedDict, total=False):
    """Template context contributions from the nav_helpers plugin.

    [attributes]
    `breadcrumbs` (list[dict]):: Hierarchical ancestor trail from root to current page.
    `nav_tree_flat` (list[dict]):: Flattened navigation tree items with depth metadata.
    """

    breadcrumbs: list[BreadcrumbItem]
    nav_tree_flat: list[NavFlatItem]


NavHelpersContribution = NavHelpersContext


class IndexContext(TypedDict, total=False):
    """Template context contributions from the index plugin.

    [attributes]
    `site_index` (dict[str, dict]):: Alphabetized index entries grouped by letter.
    """

    site_index: dict[str, dict[str, Any]]


IndexContribution = IndexContext


class GlossaryContext(TypedDict, total=False):
    """Template context contributions from the glossary plugin.

    [attributes]
    `site_glossary` (dict[str, list[dict]]):: Alphabetized glossary entries grouped by letter.
    """

    site_glossary: dict[str, list[GlossaryEntry]] | dict[str, list[dict[str, Any]]]


GlossaryContribution = GlossaryContext


class PageContext(
    SourceLinksContext,
    NavHelpersContext,
    IndexContext,
    GlossaryContext,
    total=False,
):
    """Per-document context prepared before template compilation.

    Passed into `on_template_context` lifecycle hooks for enrichment.

    [attributes]
    `title` (str):: Active page heading extracted from document header.
    `body_html` (str):: Pre-rendered semantic HTML body content.
    `toc_html` (str):: Rendered unordered list of on-page headings.
    `nav_html` (str):: Pre-rendered navigation HTML markup.
    `nav_tree` (list[dict]):: Hierarchical navigation tree items ({title, url, path, children}).
    `current_path` (str):: Relative path of the source document.
    `root_path` (str):: Relative path prefix back to site root.
    `prev_page` (dict | None):: Previous document link ({title, url}).
    `next_page` (dict | None):: Next document link ({title, url}).
    `body_class` (str | None):: CSS classes applied to <body>.
    `content_class` (str | None):: Additional CSS classes applied to <main>.
    `doc_attributes` (dict[str, Any]):: Resolved document attributes from ASG.
    `page_role` (str | None):: Declared role of the page.
    `url` (str | None):: Relative canonical URL of the compiled page.
    """

    title: str
    body_html: str
    toc_html: str
    nav_html: str
    nav_tree: list[NavTreeItem]
    current_path: str
    root_path: str
    prev_page: PageLink | None
    next_page: PageLink | None
    body_class: str | None
    content_class: str | None
    doc_attributes: dict[str, Any]
    page_role: str | None
    url: str | None


class TemplateContext(
    PageContext,
    total=False,
):
    """Foundational template context contract for Chameleon HTML5 layout rendering.

    Defines both core engine variables and plugin-injected context variables
    consumed by `skeleton.pt` and custom themes.

    [attributes]
    `title` (str):: Active page heading extracted from document header.
    `site_title` (str):: Global site title from golem.toml / pyproject.toml.
    `site_author` (str):: Global author or organization name.
    `site_url` (str | None):: Canonical site root URL.
    `generator_version` (str):: Running Golem version string.
    `root_path` (str):: Relative path prefix back to site root.
    `current_path` (str):: Relative path of the source document.
    `body_html` (str):: Pre-rendered semantic HTML body content.
    `nav_tree` (list[dict]):: Hierarchical navigation tree items ({title, url, path, children}).
    `nav_html` (str):: Pre-rendered navigation HTML markup.
    `toc_html` (str):: Rendered unordered list of on-page headings.
    `prev_page` (dict | None):: Previous document link ({title, url}).
    `next_page` (dict | None):: Next document link ({title, url}).
    `custom_css` (list[str]):: External stylesheet URLs to inject.
    `custom_js` (list[str]):: External JavaScript URLs to inject.
    `pygments_css` (str | None):: Code syntax highlighting CSS rules.
    `body_class` (str | None):: CSS classes applied to <body>.
    `content_class` (str | None):: Additional CSS classes applied to <main>.
    `breadcrumbs` (list[dict]):: Hierarchical ancestor trail from root to current page.
    `source_edit_url` (str | None):: Canonical web URL to edit source file in git host.
    `source_view_url` (str | None):: Canonical web URL to view raw source file.
    `source_repo_url` (str | None):: Canonical web URL to the source repository.
    `site_index` (dict[str, dict]):: Alphabetized index entries grouped by letter.
    `site_glossary` (dict[str, list[dict]]):: Alphabetized glossary entries grouped by letter.
    """

    site_title: str
    site_author: str
    site_url: str | None
    generator_version: str
    root_path: str
    custom_css: list[str]
    custom_js: list[str]
    pygments_css: str | None
    default_layout: Any
