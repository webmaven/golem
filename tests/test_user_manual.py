"""
= Tests for User Guide & Reference Documentation

This module verifies that docs/user-guide/ and docs/reference/ compile cleanly and comprehensively
cover all required Golem features, configuration schemas, CLI commands,
partial files protocol, static asset pipeline, and error overlay mechanisms.
"""

from pathlib import Path
import asciidoctrine
from golem.config import GolemConfig
from golem.engine import BuildEngine


def test_user_manual_compiles_and_covers_all_specifications(tmp_path):
    user_guide_dir = Path("docs/user-guide")
    ref_dir = Path("docs/reference")
    assert user_guide_dir.exists(), "docs/user-guide must exist"
    assert ref_dir.exists(), "docs/reference must exist"

    adoc_files = list(user_guide_dir.glob("*.adoc")) + list(ref_dir.glob("*.adoc"))
    assert len(adoc_files) >= 5, "Must have comprehensive user-guide and reference pages"

    all_content = []
    for doc in adoc_files:
        c = doc.read_text(encoding="utf-8")
        # 1. Verify AsciiDoc syntax parseability
        ast = asciidoctrine.parse_to_ast(c)
        assert ast is not None, f"Failed to parse {doc}"
        all_content.append(c)

    content = "\n\n".join(all_content)

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
    assert any("user-guide/index.html" in str(p) or "user-guide/configuration.html" in str(p) for p in compiled)

    # 3. Check for Project Configuration documentation
    assert "[site]" in content or "golem.toml" in content
    assert "site_url" in content
    assert "[build]" in content
    assert "content_dir" in content
    assert "output_dir" in content
    assert "theme" in content
    assert "static_dir" in content
    assert "strict" in content
    assert "[navigation]" in content
    assert "nav" in content
    assert "[plugins]" in content
    assert "golem.plugins.doctest" in content
    assert "golem.plugins.apidoc" in content
    assert "pyproject.toml" in content
    assert "[tool.golem" in content

    # 4. Check Partial Files Protocol documentation
    assert "_*.adoc" in content or "Partial Files" in content
    assert ".golem/cache.json" in content
    assert "dist/" in content

    # 5. Check Static Assets Pipeline documentation
    assert "dist/static/" in content or "static/" in content
    assert "precedence" in content.lower() or "overrides" in content.lower()

    # 6. Check Live-Reload & Error Overlay documentation
    assert "golem serve" in content
    assert "SSE" in content or "Server-Sent Events" in content
    assert "golem-error-overlay" in content

    # 7. Check CLI Command Reference
    assert "golem init" in content
    assert "golem new" in content
    assert "golem build" in content
    assert "golem serve" in content
    assert "golem plugins" in content
    assert "golem themes" in content
    assert "file:line:col" in content or ":line:column" in content or "coordinate" in content.lower()
