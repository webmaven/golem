"""
= Tests for Developer & Plugin/Theme Author Guide Documentation

This module verifies that docs/developer_guide.adoc compiles cleanly and comprehensively
covers Golem architecture, pipeline lifecycle, theme development & design philosophy,
Pluggy plugin system, hook specifications, and concrete real-world plugin recipes.
"""

from pathlib import Path
import asciidoctrine
from golem.config import GolemConfig
from golem.engine import BuildEngine


def test_developer_guide_compiles_and_covers_all_specifications(tmp_path):
    guide_path = Path("docs/developer_guide.adoc")
    assert guide_path.exists(), "docs/developer_guide.adoc must exist"

    content = guide_path.read_text(encoding="utf-8")

    # 1. Verify AsciiDoc syntax parseability
    ast = asciidoctrine.parse_to_ast(content)
    assert ast is not None

    # 2. Test compilation via BuildEngine in isolated output
    docs_dir = Path("docs").resolve()
    out_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(docs_dir),
        output_dir=str(out_dir),
        strict=True,
    )
    engine = BuildEngine(config, cache_file=tmp_path / "cache.json")
    compiled = engine.build_site()
    assert len(engine.errors) == 0, f"Compilation errors: {engine.errors}"
    assert any("developer_guide.html" in str(p) for p in compiled)

    # 3. Verify Architecture & Pipeline Lifecycle coverage
    assert "asciidoctrine" in content
    assert "Lark" in content or "Parsing" in content
    assert "AST" in content
    assert "ASG" in content or "Semantic Resolver" in content
    assert "AsciiDoctypeRenderer" in content or "asciidoctype" in content
    assert "Chameleon" in content
    assert "TAL" in content or "skeleton.pt" in content

    # 4. Verify Theme Architecture & Design Philosophy coverage
    assert "skeleton.pt" in content
    assert "templates/" in content or "templates/*.html" in content
    assert "theme.css" in content or "Custom Properties" in content
    assert "site_title" in content
    assert "page_title" in content
    assert "body_html" in content or "body_content" in content
    assert "nav_tree" in content
    assert "nav_html" in content
    assert "toc_html" in content
    assert "custom_css" in content
    assert "custom_js" in content
    assert "generator_version" in content
    assert "pyproject.toml" in content

    # 5. Verify Plugin Development Guide & Pluggy Hook Specs coverage
    assert "plugins/" in content
    assert 'golem.plugins' in content or "entry-points" in content or "entry_points" in content
    assert "pluggy" in content.lower() or "hookimpl" in content
    assert "golem_add_subcommands" in content
    assert "on_pre_parse" in content
    assert "on_ast_created" in content
    assert "on_asg_created" in content
    assert "on_post_render" in content
    assert "on_build_completed" in content

    # 6. Verify Concrete Real-World Recipes coverage
    # Recipe 1: AST Macro Transformer
    assert "Macro" in content or "alert" in content or "badge" in content
    # Recipe 2: CLI Subcommand Injection
    assert "click" in content or "subcommand" in content.lower()
    # Recipe 3: AsciiDoctype Node Template Overrides
    assert "asciidoctype" in content.lower() or "template" in content.lower()
    # Recipe 4: Build Lifecycle Hooks
    assert "sitemap" in content.lower() or "search" in content.lower() or "index" in content.lower()
