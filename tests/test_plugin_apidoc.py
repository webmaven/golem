from __future__ import annotations

import click
from click.testing import CliRunner

from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins import get_plugin_manager


def test_apidoc_plugin_registration():
    from golem.plugins import apidoc

    pm = get_plugin_manager()
    pm.register(apidoc)
    assert pm.is_registered(apidoc)


def test_on_pre_parse_macro_replacement(tmp_path):
    from golem.plugins import apidoc

    # Create a target package to document
    pkg_dir = tmp_path / "calc_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Calculator module."""
def multiply(x: int, y: int) -> int:
    """Multiply two numbers.

    Args:
        x: First factor.
        y: Second factor.

    Returns:
        Product of x and y.
    """
    return x * y
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Arithmetic Guide

Here is our multiply function:

golem:apidoc[target="calc_pkg.multiply"]

And more content.
"""
        # Initialize plugin or call on_pre_parse directly
        res = apidoc.on_pre_parse(raw_content=raw_doc)
        assert "golem:apidoc" not in res
        assert "def multiply(x: int, y: int) -> int:" in res
        assert "Multiply two numbers." in res
        assert "Arithmetic Guide" in res
    finally:
        sys.path.remove(str(tmp_path))


def test_on_pre_parse_syntax_variants(tmp_path):
    from golem.plugins import apidoc

    pkg_dir = tmp_path / "syn_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Syntax test pkg."""
def test_fn() -> None:
    """A test function."""
    pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        variants = [
            'golem:apidoc[target="syn_pkg.test_fn"]',
            "golem:apidoc[target='syn_pkg.test_fn']",
            'golem:apidoc["syn_pkg.test_fn"]',
            "golem:apidoc[syn_pkg.test_fn]",
            'golem:apidoc[target="syn_pkg.test_fn", depth="summary"]',
        ]
        for v in variants:
            raw = f"= Page\n\n{v}\n"
            out = apidoc.on_pre_parse(raw_content=raw)
            assert "golem:apidoc" not in out
            assert "test_fn" in out
    finally:
        sys.path.remove(str(tmp_path))


def test_on_pre_parse_missing_symbol_graceful():
    from golem.plugins import apidoc

    raw = '= Missing Page\n\ngolem:apidoc[target="nonexistent_pkg_123.fake_func"]\n'
    out = apidoc.on_pre_parse(raw_content=raw)
    assert "golem:apidoc" not in out
    assert "nonexistent_pkg_123.fake_func" in out


def test_apidoc_cli_subcommand(tmp_path):
    from golem.plugins import apidoc

    pkg_dir = tmp_path / "cli_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""CLI target package."""
def cli_action() -> str:
    """Perform action."""
    return "done"
''',
        encoding="utf-8",
    )

    out_dir = tmp_path / "api_out"

    @click.group()
    def cli():
        pass

    apidoc.golem_add_subcommands(cli)

    runner = CliRunner()
    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        result = runner.invoke(cli, ["apidoc", "cli_pkg", "-o", str(out_dir)])
        assert result.exit_code == 0
        assert out_dir.exists()
        adoc_files = list(out_dir.glob("*.adoc"))
        assert len(adoc_files) >= 1
    finally:
        sys.path.remove(str(tmp_path))


def test_build_engine_integration_with_apidoc(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    dist_dir = tmp_path / "dist"

    doc_text = """= Golem Config Guide

Documentation for configuration:

golem:apidoc[target="golem.config.GolemConfig"]
"""
    (content_dir / "index.adoc").write_text(doc_text, encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(dist_dir),
        plugins=["golem.plugins.apidoc"],
    )

    engine = BuildEngine(config)
    engine.build_site()

    out_html = (dist_dir / "index.html").read_text(encoding="utf-8")
    assert "Golem Config Guide" in out_html
    assert "GolemConfig" in out_html
    assert "site_title" in out_html
