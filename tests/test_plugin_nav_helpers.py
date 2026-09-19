"""Tests for NavigationHelpersPlugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins.nav_helpers import NavigationHelpersPlugin


def test_breadcrumbs_home_only():
    plugin = NavigationHelpersPlugin()
    context: dict[str, Any] = {"title": "Home", "current_path": "index.adoc"}
    result = plugin.on_template_context(context, Path("index.adoc"))
    assert "breadcrumbs" in result
    assert result["breadcrumbs"] == [{"title": "Home", "url": "/", "is_current": True}]


def test_breadcrumbs_flat_list():
    plugin = NavigationHelpersPlugin()
    nav_tree = [
        {"title": "About", "path": "about.adoc", "url": "about.html", "children": []},
        {"title": "Contact", "path": "contact.adoc", "url": "contact.html", "children": []},
    ]
    context: dict[str, Any] = {
        "title": "About",
        "current_path": "about.adoc",
        "nav_tree": nav_tree,
    }
    result = plugin.on_template_context(context, Path("about.adoc"))
    assert result["breadcrumbs"] == [
        {"title": "Home", "url": "/", "is_current": False},
        {"title": "About", "url": "about.html", "is_current": True},
    ]


def test_breadcrumbs_nested():
    plugin = NavigationHelpersPlugin()
    nav_tree = [
        {
            "title": "Guide",
            "path": "guide/index.adoc",
            "url": "guide/",
            "children": [
                {
                    "title": "Advanced",
                    "path": "guide/advanced/index.adoc",
                    "url": "guide/advanced/",
                    "children": [
                        {
                            "title": "Performance",
                            "path": "guide/advanced/perf.adoc",
                            "url": "guide/advanced/perf.html",
                            "children": [],
                        }
                    ],
                }
            ],
        }
    ]
    context: dict[str, Any] = {
        "title": "Performance",
        "current_path": "guide/advanced/perf.adoc",
        "nav_tree": nav_tree,
    }
    result = plugin.on_template_context(context, Path("guide/advanced/perf.adoc"))
    assert result["breadcrumbs"] == [
        {"title": "Home", "url": "/", "is_current": False},
        {"title": "Guide", "url": "guide/", "is_current": False},
        {"title": "Advanced", "url": "guide/advanced/", "is_current": False},
        {"title": "Performance", "url": "guide/advanced/perf.html", "is_current": True},
    ]


def test_breadcrumbs_not_found():
    plugin = NavigationHelpersPlugin()
    nav_tree = [{"title": "Overview", "path": "overview.adoc", "url": "overview.html", "children": []}]
    context: dict[str, Any] = {
        "title": "Secret Page",
        "current_path": "secret.adoc",
        "nav_tree": nav_tree,
    }
    result = plugin.on_template_context(context, Path("secret.adoc"))
    assert result["breadcrumbs"] == [
        {"title": "Home", "url": "/", "is_current": False},
        {"title": "Secret Page", "url": "secret.html", "is_current": True},
    ]


def test_nav_tree_flat_dfs_order():
    plugin = NavigationHelpersPlugin()
    nav_tree = [
        {
            "title": "Chapter 1",
            "url": "ch1/",
            "children": [
                {"title": "Section 1.1", "url": "ch1/s1.html", "children": []},
                {
                    "title": "Section 1.2",
                    "url": "ch1/s2.html",
                    "children": [{"title": "Subsection 1.2.1", "url": "ch1/s2-1.html", "children": []}],
                },
            ],
        },
        {"title": "Chapter 2", "url": "ch2/", "children": []},
    ]
    context: dict[str, Any] = {"nav_tree": nav_tree, "current_path": "index.adoc"}
    result = plugin.on_template_context(context, Path("index.adoc"))
    assert "nav_tree_flat" in result
    titles = [item["title"] for item in result["nav_tree_flat"]]
    assert titles == [
        "Chapter 1",
        "Section 1.1",
        "Section 1.2",
        "Subsection 1.2.1",
        "Chapter 2",
    ]


def test_nav_tree_flat_depth_values():
    plugin = NavigationHelpersPlugin()
    nav_tree = [
        {
            "title": "Level 0",
            "url": "l0/",
            "children": [
                {
                    "title": "Level 1",
                    "url": "l1/",
                    "children": [{"title": "Level 2", "url": "l2/", "children": []}],
                }
            ],
        }
    ]
    context: dict[str, Any] = {"nav_tree": nav_tree, "current_path": "index.adoc"}
    result = plugin.on_template_context(context, Path("index.adoc"))
    depths = [item["depth"] for item in result["nav_tree_flat"]]
    assert depths == [0, 1, 2]
    assert result["nav_tree_flat"][0] == {"title": "Level 0", "url": "l0/", "depth": 0}
    assert result["nav_tree_flat"][1] == {"title": "Level 1", "url": "l1/", "depth": 1}
    assert result["nav_tree_flat"][2] == {"title": "Level 2", "url": "l2/", "depth": 2}


def test_does_not_overwrite_existing_prev_next():
    plugin = NavigationHelpersPlugin()
    prev = {"title": "Existing Prev", "url": "prev.html"}
    next_p = {"title": "Existing Next", "url": "next.html"}
    nav_tree = [
        {"title": "Page 1", "path": "p1.adoc", "url": "p1.html", "children": []},
        {"title": "Page 2", "path": "p2.adoc", "url": "p2.html", "children": []},
        {"title": "Page 3", "path": "p3.adoc", "url": "p3.html", "children": []},
    ]
    context: dict[str, Any] = {
        "current_path": "p2.adoc",
        "prev_page": prev,
        "next_page": next_p,
        "nav_tree": nav_tree,
    }
    result = plugin.on_template_context(context, Path("p2.adoc"))
    assert result["prev_page"] is prev
    assert result["next_page"] is next_p


def test_home_url_from_context_root_path():
    plugin = NavigationHelpersPlugin()
    context: dict[str, Any] = {
        "title": "Sub Page",
        "current_path": "deep/nested/page.adoc",
        "root_path": "../../",
    }
    result = plugin.on_template_context(context, Path("deep/nested/page.adoc"))
    assert result["breadcrumbs"][0]["url"] == "../../"
    assert result["breadcrumbs"][0]["title"] == "Home"

    # Explicit home_url overrides root_path
    custom_plugin = NavigationHelpersPlugin(home_title="Start", home_url="https://example.com/docs/")
    res_custom = custom_plugin.on_template_context(context, Path("deep/nested/page.adoc"))
    assert res_custom["breadcrumbs"][0]["url"] == "https://example.com/docs/"
    assert res_custom["breadcrumbs"][0]["title"] == "Start"


def test_duck_typed_navigation_entries():
    class DummyEntry:
        def __init__(self, title: str, path: str, url: str, children: list[Any] | None = None) -> None:
            self.title = title
            self.path = path
            self.url = url
            self.children = children or []

    entry_child = DummyEntry("Child Page", "section/child.adoc", "section/child.html")
    entry_parent = DummyEntry("Section", "section/index.adoc", "section/", [entry_child])
    nav_tree = [entry_parent]

    plugin = NavigationHelpersPlugin()
    context: dict[str, Any] = {
        "title": "Child Page",
        "current_path": "section/child.adoc",
        "nav_tree": nav_tree,
    }
    result = plugin.on_template_context(context, Path("section/child.adoc"))
    assert result["breadcrumbs"] == [
        {"title": "Home", "url": "/", "is_current": False},
        {"title": "Section", "url": "section/", "is_current": False},
        {"title": "Child Page", "url": "section/child.html", "is_current": True},
    ]
    assert len(result["nav_tree_flat"]) == 2
    assert result["nav_tree_flat"][0] == {"title": "Section", "url": "section/", "depth": 0}
    assert result["nav_tree_flat"][1] == {"title": "Child Page", "url": "section/child.html", "depth": 1}


def test_integration_with_engine(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Home\n\nWelcome home.", encoding="utf-8")
    docs_dir = content_dir / "guide"
    docs_dir.mkdir()
    (docs_dir / "index.adoc").write_text("= User Guide\n\nGuide content.", encoding="utf-8")
    (docs_dir / "intro.adoc").write_text("= Intro Page\n\nIntroduction.", encoding="utf-8")

    out_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(out_dir),
        site_title="Test Site",
    )
    engine = BuildEngine(config)
    plugin = NavigationHelpersPlugin()
    engine.pm.register(plugin)

    compiled = engine.build_site()
    assert len(compiled) > 0

    # Check that intro.html contains the breadcrumbs navigation
    intro_html = (out_dir / "guide" / "intro.html").read_text(encoding="utf-8")
    assert 'class="golem-breadcrumbs"' in intro_html or "golem-breadcrumbs" in intro_html
    assert 'aria-label="Breadcrumb"' in intro_html
    assert 'aria-current="page"' in intro_html
    assert "Home" in intro_html
    assert "User Guide" in intro_html
    assert "Intro Page" in intro_html


def test_navigation_helpers_plugin_inheritance():
    from golem.plugins import GolemPlugin

    assert issubclass(NavigationHelpersPlugin, GolemPlugin)
    assert NavigationHelpersPlugin.name == "nav_helpers"
    plugin = NavigationHelpersPlugin()
    assert plugin.name == "nav_helpers"


def test_find_chain_edge_cases():
    from golem.plugins.nav_helpers import _find_chain

    assert _find_chain([], "index.adoc", Path("index.adoc")) is None
    assert _find_chain([{"title": "Other", "path": "other.adoc"}], "index.adoc", Path("index.adoc")) is None
