"""End-to-end integration tests for Golem bundled plugins.

Verifies that bundled plugins (source_links, nav_helpers, index, glossary)
can be configured purely through GolemConfig(plugins=[...], plugin_configs={...})
or golem.toml without any manual engine.pm.register(...) calls.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from golem.cli import main
from golem.config import GolemConfig
from golem.engine import BuildEngine


def test_e2e_source_links_via_config(tmp_path: Path) -> None:
    """Verify source_links is activated and configured purely via GolemConfig.

    Builds a mock site and asserts that source_edit_url is rendered in the HTML.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text(
        "= Documentation Home\n\nWelcome to our project docs.\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["source_links"],
        plugin_configs={
            "source_links": {
                "repo_url": "https://github.com/webmaven/golem",
                "branch": "main",
                "docs_dir": "content",
            }
        },
    )

    engine = BuildEngine(config)
    compiled = engine.build_site()
    assert len(compiled) == 1

    index_html = (output_dir / "index.html").read_text(encoding="utf-8")
    assert "golem-edit-link" in index_html
    assert "https://github.com/webmaven/golem/edit/main/content/index.adoc" in index_html


def test_e2e_nav_helpers_via_config(tmp_path: Path) -> None:
    """Verify nav_helpers is activated purely via GolemConfig.

    Builds nested pages and asserts that breadcrumbs are rendered in the HTML for child pages.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Site Home\n\nRoot index.\n", encoding="utf-8")

    guide_dir = content_dir / "guide"
    guide_dir.mkdir()
    (guide_dir / "index.adoc").write_text("= User Guide\n\nGuide overview.\n", encoding="utf-8")
    (guide_dir / "quickstart.adoc").write_text("= Quickstart\n\nGetting started quickly.\n", encoding="utf-8")

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["nav_helpers"],
    )

    engine = BuildEngine(config)
    compiled = engine.build_site()
    assert len(compiled) == 3

    quickstart_html = (output_dir / "guide" / "quickstart.html").read_text(encoding="utf-8")
    assert "golem-breadcrumbs" in quickstart_html
    assert 'aria-label="Breadcrumb"' in quickstart_html
    assert "Site Home" in quickstart_html or "Home" in quickstart_html
    assert "User Guide" in quickstart_html
    assert "Quickstart" in quickstart_html


def test_e2e_index_via_config(tmp_path: Path) -> None:
    """Verify index plugin is activated purely via GolemConfig.

    Builds documentation pages with ((terms)) and verifies that only the page
    declaring :page-role: index receives site_index in its rendered HTML.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    (content_dir / "compiler.adoc").write_text(
        "= Compiler Architecture\n\nCovers the ((Compiler)) and ((AST)).\n",
        encoding="utf-8",
    )
    (content_dir / "parser.adoc").write_text(
        "= Parser Details\n\nDiscusses the ((Parser)) and ((Grammar)).\n",
        encoding="utf-8",
    )
    (content_dir / "index_page.adoc").write_text(
        "= Subject Index\n:page-role: index\n\nAlphabetical index of all topics.\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["index"],
    )

    engine = BuildEngine(config)
    compiled = engine.build_site()
    assert len(compiled) == 3

    # Index page MUST contain compiled site_index
    index_page_html = (output_dir / "index_page.html").read_text(encoding="utf-8")
    assert "site-index" in index_page_html
    assert "Compiler" in index_page_html
    assert "AST" in index_page_html
    assert "Parser" in index_page_html
    assert "Grammar" in index_page_html

    # Content pages MUST NOT have site-index rendered
    compiler_html = (output_dir / "compiler.html").read_text(encoding="utf-8")
    assert "site-index" not in compiler_html
    parser_html = (output_dir / "parser.html").read_text(encoding="utf-8")
    assert "site-index" not in parser_html


def test_e2e_glossary_via_config(tmp_path: Path) -> None:
    """Verify glossary plugin is activated purely via GolemConfig.

    Builds documentation pages with [glossary] description lists and verifies
    that only the page declaring :page-role: glossary receives site_glossary.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    (content_dir / "standards.adoc").write_text(
        """= Technical Standards

[glossary]
API:: Application Programming Interface
CLI:: Command Line Interface
""",
        encoding="utf-8",
    )
    (content_dir / "formats.adoc").write_text(
        """= Data Formats

[glossary]
JSON:: JavaScript Object Notation
""",
        encoding="utf-8",
    )
    (content_dir / "glossary_page.adoc").write_text(
        """= Glossary of Terms
:page-role: glossary

Complete glossary definitions.
""",
        encoding="utf-8",
    )

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["glossary"],
    )

    engine = BuildEngine(config)
    compiled = engine.build_site()
    assert len(compiled) == 3

    # Glossary page MUST contain compiled site_glossary
    glossary_html = (output_dir / "glossary_page.html").read_text(encoding="utf-8")
    assert "site-glossary" in glossary_html
    assert "API" in glossary_html
    assert "Application Programming Interface" in glossary_html
    assert "CLI" in glossary_html
    assert "JSON" in glossary_html

    # Content page without glossary role MUST NOT have site-glossary rendered
    formats_html = (output_dir / "formats.html").read_text(encoding="utf-8")
    assert "site-glossary" not in formats_html


def test_e2e_all_bundled_plugins_active(tmp_path: Path) -> None:
    """Verify all 4 bundled plugins operate concurrently without conflict.

    Exercises source_links, nav_helpers, index, and glossary simultaneously.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    (content_dir / "index.adoc").write_text(
        "= Portal Home\n\nWelcome to the developer portal.\n",
        encoding="utf-8",
    )

    docs_dir = content_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.adoc").write_text(
        """= User Guide

[glossary]
SDK:: Software Development Kit

Here is our discussion of ((Pipelines)) and ((Rendering)).
""",
        encoding="utf-8",
    )

    (content_dir / "site_index.adoc").write_text(
        "= Master Index\n:page-role: index\n\nFull index.\n",
        encoding="utf-8",
    )
    (content_dir / "site_glossary.adoc").write_text(
        "= Master Glossary\n:page-role: glossary\n\nFull glossary.\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["source_links", "nav_helpers", "index", "glossary"],
        plugin_configs={
            "source_links": {
                "repo_url": "https://github.com/webmaven/golem",
                "branch": "main",
                "docs_dir": "content",
            }
        },
    )

    engine = BuildEngine(config)
    compiled = engine.build_site()
    assert len(compiled) == 4

    # 1. Check nested guide page: has breadcrumbs, source_links, but no site-index or site-glossary
    guide_html = (output_dir / "docs" / "guide.html").read_text(encoding="utf-8")
    assert "golem-breadcrumbs" in guide_html
    assert "golem-edit-link" in guide_html
    assert "https://github.com/webmaven/golem/edit/main/content/docs/guide.adoc" in guide_html
    assert "site-index" not in guide_html
    assert "site-glossary" not in guide_html

    # 2. Check site_index page: has site-index with Pipelines and Rendering
    idx_html = (output_dir / "site_index.html").read_text(encoding="utf-8")
    assert "site-index" in idx_html
    assert "Pipelines" in idx_html
    assert "Rendering" in idx_html
    assert "site-glossary" not in idx_html

    # 3. Check site_glossary page: has site-glossary with SDK
    glo_html = (output_dir / "site_glossary.html").read_text(encoding="utf-8")
    assert "site-glossary" in glo_html
    assert "SDK" in glo_html
    assert "Software Development Kit" in glo_html
    assert "site-index" not in glo_html


def test_e2e_cli_build_with_golem_toml_plugins(tmp_path: Path) -> None:
    """Verify full CLI `golem build` with golem.toml [plugins] configuration."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    content_dir = project_dir / "docs"
    content_dir.mkdir()

    (content_dir / "index.adoc").write_text("= Home\n\nWelcome.\n", encoding="utf-8")
    guide_dir = content_dir / "guide"
    guide_dir.mkdir()
    (guide_dir / "nested.adoc").write_text(
        """= Nested Guide

[glossary]
REPL:: Read Eval Print Loop

A discussion of ((Bytecode)).
""",
        encoding="utf-8",
    )
    (content_dir / "idx.adoc").write_text("= Index\n:page-role: index\n\nIndex page.\n", encoding="utf-8")
    (content_dir / "glo.adoc").write_text("= Glossary\n:page-role: glossary\n\nGlossary page.\n", encoding="utf-8")

    (project_dir / "golem.toml").write_text(
        """[site]
title = "CLI Integration Site"

[build]
content_dir = "docs"
output_dir = "dist"

[plugins]
plugins = ["source_links", "nav_helpers", "index", "glossary"]

[plugins.source_links]
repo_url = "https://github.com/webmaven/golem"
branch = "release-1.0"
docs_dir = "docs"

[plugins.nav_helpers]
home_title = "Start"
""",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["build", "-C", str(project_dir)])
    assert result.exit_code == 0, f"golem build failed: {result.output}"

    dist_dir = project_dir / "dist"
    nested_html = (dist_dir / "guide" / "nested.html").read_text(encoding="utf-8")
    assert "golem-breadcrumbs" in nested_html
    assert "Start" in nested_html
    assert "https://github.com/webmaven/golem/edit/release-1.0/docs/guide/nested.adoc" in nested_html

    idx_html = (dist_dir / "idx.html").read_text(encoding="utf-8")
    assert "site-index" in idx_html
    assert "Bytecode" in idx_html

    glo_html = (dist_dir / "glo.html").read_text(encoding="utf-8")
    assert "site-glossary" in glo_html
    assert "REPL" in glo_html
    assert "Read Eval Print Loop" in glo_html
