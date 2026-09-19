"""Tests for TemplateContext, PageContext, and plugin context contracts."""

from pathlib import Path
from typing import get_type_hints, is_typeddict

from golem.model import (
    BreadcrumbItem,
    GlossaryContext,
    GlossaryEntry,
    IndexContext,
    NavFlatItem,
    NavHelpersContext,
    NavTreeItem,
    PageContext,
    PageLink,
    SourceLinksContext,
    TemplateContext,
)
from golem.plugins import GolemSpecs
from golem.plugins.index_glossary import GlossaryPlugin, IndexPlugin
from golem.plugins.nav_helpers import NavigationHelpersPlugin
from golem.plugins.source_links import SourceLinksPlugin


def test_template_context_is_typeddict():
    """Verify TemplateContext is a TypedDict."""
    assert is_typeddict(TemplateContext), "TemplateContext must be a TypedDict"


def test_template_context_contains_all_skeleton_core_keys():
    """Verify TemplateContext contains all core keys defined in skeleton.pt."""
    required_skeleton_keys = {
        "title",
        "site_title",
        "root_path",
        "current_path",
        "body_html",
        "nav_tree",
        "nav_html",
        "toc_html",
        "breadcrumbs",
        "source_edit_url",
        "site_index",
        "site_glossary",
    }
    annotations = TemplateContext.__annotations__
    missing_keys = required_skeleton_keys - set(annotations.keys())
    assert not missing_keys, f"TemplateContext missing core skeleton.pt keys: {missing_keys}"


def test_template_context_contains_full_skeleton_variables():
    """Verify TemplateContext contains all variables documented in skeleton.pt."""
    full_skeleton_keys = {
        # Core Engine Variables
        "title",
        "site_title",
        "site_author",
        "site_url",
        "generator_version",
        "root_path",
        "current_path",
        "body_html",
        "nav_tree",
        "nav_html",
        "toc_html",
        "prev_page",
        "next_page",
        "custom_css",
        "custom_js",
        "pygments_css",
        "body_class",
        "content_class",
        # Plugin-Injected Variables
        "breadcrumbs",
        "source_edit_url",
        "source_view_url",
        "source_repo_url",
        "site_index",
        "site_glossary",
    }
    annotations = TemplateContext.__annotations__
    missing = full_skeleton_keys - set(annotations.keys())
    assert not missing, f"TemplateContext missing skeleton.pt variables: {missing}"


def test_page_context_is_typeddict():
    """Verify PageContext is a TypedDict with expected page-level keys."""
    assert is_typeddict(PageContext), "PageContext must be a TypedDict"
    expected_keys = {
        "title",
        "body_html",
        "toc_html",
        "nav_html",
        "nav_tree",
        "current_path",
        "prev_page",
        "next_page",
        "body_class",
        "content_class",
        "doc_attributes",
    }
    assert expected_keys.issubset(set(PageContext.__annotations__.keys()))


def test_subdicts_are_typeddicts():
    """Verify sub-dicts representing structured items are TypedDicts."""
    assert is_typeddict(NavTreeItem)
    assert is_typeddict(PageLink)
    assert is_typeddict(BreadcrumbItem)
    assert is_typeddict(NavFlatItem)
    assert is_typeddict(GlossaryEntry)

    # NavTreeItem fields
    assert "title" in NavTreeItem.__annotations__
    assert "url" in NavTreeItem.__annotations__

    # PageLink fields
    assert "title" in PageLink.__annotations__
    assert "url" in PageLink.__annotations__

    # BreadcrumbItem fields
    assert "title" in BreadcrumbItem.__annotations__
    assert "url" in BreadcrumbItem.__annotations__
    assert "is_current" in BreadcrumbItem.__annotations__

    # NavFlatItem fields
    assert "title" in NavFlatItem.__annotations__
    assert "url" in NavFlatItem.__annotations__
    assert "depth" in NavFlatItem.__annotations__

    # GlossaryEntry fields
    assert "term" in GlossaryEntry.__annotations__
    assert "definition" in GlossaryEntry.__annotations__


def test_plugin_contribution_typeddicts():
    """Verify plugin context contribution TypedDicts."""
    assert is_typeddict(SourceLinksContext)
    assert "source_repo_url" in SourceLinksContext.__annotations__
    assert "source_edit_url" in SourceLinksContext.__annotations__
    assert "source_view_url" in SourceLinksContext.__annotations__

    assert is_typeddict(NavHelpersContext)
    assert "breadcrumbs" in NavHelpersContext.__annotations__
    assert "nav_tree_flat" in NavHelpersContext.__annotations__

    assert is_typeddict(IndexContext)
    assert "site_index" in IndexContext.__annotations__

    assert is_typeddict(GlossaryContext)
    assert "site_glossary" in GlossaryContext.__annotations__


def test_golem_specs_on_template_context_typed():
    """Verify GolemSpecs.on_template_context uses PageContext."""
    hints = get_type_hints(GolemSpecs.on_template_context)
    assert hints.get("context") is PageContext
    assert hints.get("doc_path") is Path


def test_plugin_implementations_on_template_context_typed():
    """Verify bundled plugin on_template_context implementations use PageContext."""
    for plugin_cls in (SourceLinksPlugin, NavigationHelpersPlugin, IndexPlugin, GlossaryPlugin):
        hints = get_type_hints(plugin_cls.on_template_context)
        assert hints.get("context") is PageContext, f"{plugin_cls.__name__} context arg not typed with PageContext"
        assert hints.get("doc_path") is Path, f"{plugin_cls.__name__} doc_path arg not typed with Path"


def test_docstring_verbatim_alignment():
    """Verify TemplateContext docstrings describe skeleton variables with verbatim alignment."""
    doc = TemplateContext.__doc__ or ""
    skeleton_path = Path(__file__).parent.parent / "src" / "golem" / "templates" / "default" / "skeleton.pt"
    skeleton_content = skeleton_path.read_text(encoding="utf-8")

    # Key descriptions from skeleton.pt that must match verbatim
    expected_phrases = [
        "Active page heading extracted from document header.",
        "Global site title from golem.toml / pyproject.toml.",
        "Global author or organization name.",
        "Canonical site root URL.",
        "Running Golem version string.",
        "Relative path prefix back to site root.",
        "Relative path of the source document.",
        "Pre-rendered semantic HTML body content.",
        "Hierarchical navigation tree items ({title, url, path, children}).",
        "Pre-rendered navigation HTML markup.",
        "Rendered unordered list of on-page headings.",
        "Previous document link ({title, url}).",
        "Next document link ({title, url}).",
        "External stylesheet URLs to inject.",
        "External JavaScript URLs to inject.",
        "Code syntax highlighting CSS rules.",
        "CSS classes applied to <body>.",
        "Additional CSS classes applied to <main>.",
        "Hierarchical ancestor trail from root to current page.",
        "Canonical web URL to edit source file in git host.",
        "Canonical web URL to view raw source file.",
        "Canonical web URL to the source repository.",
        "Alphabetized index entries grouped by letter.",
        "Alphabetized glossary entries grouped by letter.",
    ]

    for phrase in expected_phrases:
        assert phrase in skeleton_content, f"Expected phrase not in skeleton.pt: {phrase}"
        assert phrase in doc, f"Expected phrase not in TemplateContext docstring: {phrase}"
