from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Generator
import click
import pytest
from click.testing import CliRunner

from golem.cli import main
from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins import get_plugin_manager
from golem.plugins.apidoc import generate_api_docs
from golem.plugins.doctest import run_doctests


@pytest.fixture
def sample_package(tmp_path: Path) -> Generator[dict[str, Any], None, None]:
    """Create a temporary Python package on sys.path with modules, classes, functions, and doctests."""
    pkg_dir = tmp_path / "sample_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Sample package for e2e tests."""

class Calculator:
    """A sample calculator class.

    === Examples

    [source,python,role="test"]
    ----
    >>> from sample_pkg import Calculator
    >>> calc = Calculator()
    >>> calc.add(10, 20)
    30
    ----
    """

    def add(self, a: int, b: int) -> int:
        """Add two integers.

        Args:
            a: First number.
            b: Second number.

        Returns:
            The sum of a and b.
        """
        return a + b

    def subtract(self, a: int, b: int) -> int:
        """Subtract b from a."""
        return a - b


def helper_func(text: str) -> str:
    """Transform text to uppercase.

    === Examples

    [source,python,role="test"]
    ----
    >>> from sample_pkg import helper_func
    >>> helper_func("golem")
    'GOLEM'
    ----
    """
    return text.upper()
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        yield {
            "pkg_dir": pkg_dir,
            "tmp_path": tmp_path,
            "pkg_name": "sample_pkg",
        }
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        sys.modules.pop("sample_pkg", None)
        for mod in list(sys.modules.keys()):
            if mod.startswith("sample_pkg."):
                sys.modules.pop(mod, None)


@pytest.fixture
def broken_package(tmp_path: Path) -> Generator[dict[str, Any], None, None]:
    """Create a temporary Python package with a failing doctest."""
    pkg_dir = tmp_path / "broken_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Package with broken doctest."""

def bad_math(x: int) -> int:
    """Incorrect calculation doctest.

    === Examples

    [source,python,role="test"]
    ----
    >>> from broken_pkg import bad_math
    >>> bad_math(5)
    999
    ----
    """
    return x * 2
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        yield {
            "pkg_dir": pkg_dir,
            "tmp_path": tmp_path,
            "pkg_name": "broken_pkg",
        }
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        sys.modules.pop("broken_pkg", None)
        for mod in list(sys.modules.keys()):
            if mod.startswith("broken_pkg."):
                sys.modules.pop(mod, None)


def test_e2e_full_site_build_with_api_packages(tmp_path: Path, sample_package: dict[str, Any]):
    """Scenario 1: Full Site Build with Configured api_packages.

    Verify that when api_packages is configured, BuildEngine generates API docs into
    content_dir / api_output_dir and compiles them into dist/api/sample_pkg.html.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text(
        """= Home Page

Welcome to our project documentation.
""",
        encoding="utf-8",
    )

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["golem.plugins.apidoc"],
        api_packages=["sample_pkg"],
        api_output_dir="api",
    )

    engine = BuildEngine(config)
    compiled = engine.build_site()

    # Verify that api .adoc was generated into content_dir
    api_adoc = content_dir / "api" / "sample_pkg.adoc"
    assert api_adoc.exists(), f"Expected {api_adoc} to exist"

    # Verify that HTML was generated in output_dir
    index_html = output_dir / "index.html"
    api_html = output_dir / "api" / "sample_pkg.html"
    assert index_html.exists()
    assert api_html.exists()
    assert api_html in compiled

    # Check content of compiled API documentation HTML
    api_html_content = api_html.read_text(encoding="utf-8")
    assert "Calculator" in api_html_content
    assert "add" in api_html_content
    assert "helper_func" in api_html_content
    assert "Transform text to uppercase" in api_html_content


def test_e2e_inline_apidoc_macro_in_guide(tmp_path: Path, sample_package: dict[str, Any]):
    """Scenario 2: Inline golem:apidoc[...] Macro in a Hand-Written Guide.

    Verify that golem:apidoc[...] in an AsciiDoc document is replaced during build
    and rendered into the output HTML.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "guide.adoc").write_text(
        """= Developer Guide

Here is our helper function:

golem:apidoc[target="sample_pkg.helper_func"]

End of guide.
""",
        encoding="utf-8",
    )

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["golem.plugins.apidoc"],
    )

    engine = BuildEngine(config)
    engine.build_site()

    guide_html = output_dir / "guide.html"
    assert guide_html.exists()
    guide_content = guide_html.read_text(encoding="utf-8")

    assert "golem:apidoc" not in guide_content
    assert "helper_func" in guide_content
    assert "Transform text to uppercase" in guide_content


def test_e2e_doctest_on_generated_api_docs(tmp_path: Path, sample_package: dict[str, Any]):
    """Scenario 3: golem doctest docs/ on Generated API Docs.

    Verify that doctests embedded in docstrings of generated API docs run and pass.
    """
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    # Step 1: Generate API documentation into docs_dir / "api"
    generated = generate_api_docs(
        packages=["sample_pkg"],
        output_dir=docs_dir / "api",
    )
    assert len(generated) >= 1

    # Step 2: Run doctests on the docs directory
    exit_code = run_doctests(paths=[docs_dir], mode="explicit")
    assert exit_code == 0

    # Also test via Click CLI
    @click.group()
    def cli():
        pass

    from golem.plugins import doctest

    doctest.golem_add_subcommands(cli)
    runner = CliRunner()
    res = runner.invoke(cli, ["doctest", str(docs_dir)])
    assert res.exit_code == 0


def test_e2e_doctest_on_generated_api_docs_failing(tmp_path: Path, broken_package: dict[str, Any]):
    """Scenario 3 (failure): golem doctest docs/ catches errors in generated API docs."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    generate_api_docs(
        packages=["broken_pkg"],
        output_dir=docs_dir / "api",
    )

    exit_code = run_doctests(paths=[docs_dir], mode="explicit")
    assert exit_code == 1

    @click.group()
    def cli():
        pass

    from golem.plugins import doctest

    doctest.golem_add_subcommands(cli)
    runner = CliRunner()
    res = runner.invoke(cli, ["doctest", str(docs_dir)])
    assert res.exit_code != 0


def test_e2e_doctest_source_importable_package(sample_package: dict[str, Any], broken_package: dict[str, Any]):
    """Scenario 4: golem doctest --source with an Importable Fixture Package.

    Verify running doctests directly from Python sources/packages via --source.
    """
    # 1. Passing package
    exit_code_pass = run_doctests(source="sample_pkg", mode="explicit")
    assert exit_code_pass == 0

    @click.group()
    def cli():
        pass

    from golem.plugins import doctest

    doctest.golem_add_subcommands(cli)
    runner = CliRunner()
    res_pass = runner.invoke(cli, ["doctest", "--source", "sample_pkg"])
    assert res_pass.exit_code == 0

    # 2. Deliberately broken package
    exit_code_fail = run_doctests(source="broken_pkg", mode="explicit")
    assert exit_code_fail == 1

    res_fail = runner.invoke(cli, ["doctest", "--source", "broken_pkg"])
    assert res_fail.exit_code != 0


def test_e2e_cooperative_plugins(tmp_path: Path, sample_package: dict[str, Any]):
    """Scenario 5: Cooperative Plugin Operation (both plugins active).

    Verify both plugins register subcommands without conflict and build_site works.
    """
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text(
        """= Welcome

[source,python,role="test"]
----
>>> 1 + 1
2
----
""",
        encoding="utf-8",
    )

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["golem.plugins.apidoc", "golem.plugins.doctest"],
        api_packages=["sample_pkg"],
    )

    # 1. Verify plugin manager registers both plugins
    pm = get_plugin_manager(config)
    assert pm.is_registered(sys.modules["golem.plugins.apidoc"])
    assert pm.is_registered(sys.modules["golem.plugins.doctest"])

    # 2. Verify subcommands are registered in CLI
    @click.group()
    def cli():
        pass

    pm.hook.golem_add_subcommands(cli=cli)
    runner = CliRunner()
    res = runner.invoke(cli, ["--help"])
    assert res.exit_code == 0
    assert "apidoc" in res.output
    assert "doctest" in res.output

    # 3. Build site with both plugins active
    engine = BuildEngine(config)
    compiled = engine.build_site()
    assert len(compiled) >= 2  # index.html and api/sample_pkg.html

    # 4. Run doctests on content_dir
    doctest_res = run_doctests(paths=[content_dir])
    assert doctest_res == 0


def test_e2e_custom_api_output_dir_and_multiple_packages(tmp_path: Path):
    """Test api generation with custom api_output_dir and multiple packages."""
    # Create two fixture packages
    for name in ["pkg_alpha", "pkg_beta"]:
        p_dir = tmp_path / name
        p_dir.mkdir()
        (p_dir / "__init__.py").write_text(
            f'''"""Package {name}."""
def fn_{name}() -> str:
    """Function in {name}."""
    return "{name}"
''',
            encoding="utf-8",
        )

    sys.path.insert(0, str(tmp_path))
    try:
        content_dir = tmp_path / "content"
        content_dir.mkdir()
        (content_dir / "index.adoc").write_text("= Index\n\nContent.", encoding="utf-8")

        output_dir = tmp_path / "dist"
        config = GolemConfig(
            content_dir=str(content_dir),
            output_dir=str(output_dir),
            plugins=["golem.plugins.apidoc"],
            api_packages=["pkg_alpha", "pkg_beta"],
            api_output_dir="reference/api",
        )

        engine = BuildEngine(config)
        compiled = engine.build_site()

        alpha_html = output_dir / "reference" / "api" / "pkg_alpha.html"
        beta_html = output_dir / "reference" / "api" / "pkg_beta.html"
        assert alpha_html.exists()
        assert beta_html.exists()
        assert alpha_html in compiled
        assert beta_html in compiled
        assert "fn_pkg_alpha" in alpha_html.read_text(encoding="utf-8")
        assert "fn_pkg_beta" in beta_html.read_text(encoding="utf-8")
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        sys.modules.pop("pkg_alpha", None)
        sys.modules.pop("pkg_beta", None)


def test_e2e_cli_build_with_golem_toml(tmp_path: Path, sample_package: dict[str, Any]):
    """Test full CLI `golem build` with golem.toml configuration."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    content_dir = project_dir / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Welcome to App\n\nHello world.", encoding="utf-8")

    (project_dir / "golem.toml").write_text(
        """[site]
title = "App Docs"

[build]
content_dir = "content"
output_dir = "dist"

[plugins]
plugins = ["golem.plugins.apidoc"]

[api]
packages = ["sample_pkg"]
output_dir = "api"
""",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["build", "-C", str(project_dir)])
    assert result.exit_code == 0

    api_html = project_dir / "dist" / "api" / "sample_pkg.html"
    assert api_html.exists()
    assert "Calculator" in api_html.read_text(encoding="utf-8")
