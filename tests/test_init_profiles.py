"""
= CLI Init Profile Tests for Golem

This module contains functional tests for the `golem init --profile` command,
verifying template scaffolding, variable substitution, and fallback behavior.
"""

import datetime
from pathlib import Path
import pytest
from click.testing import CliRunner
from golem.cli import main


@pytest.mark.parametrize(
    "profile,expected_paths",
    [
        (
            "library",
            [
                "docs/api/index.adoc",
                "docs/user-guide/index.adoc",
                "golem.toml",
            ],
        ),
        (
            "cli",
            [
                "docs/reference/cli.adoc",
                "docs/user-guide/index.adoc",
                "golem.toml",
            ],
        ),
        (
            "paper",
            [
                "paper.adoc",
                "refs.bib",
                "golem.toml",
            ],
        ),
        (
            "blog",
            [
                "_nav.adoc",
                "golem.toml",
            ],
        ),
    ],
)
def test_profile_creates_expected_files(profile, expected_paths):
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init", "--profile", profile], input="\n\n")
        assert result.exit_code == 0, result.output
        for path in expected_paths:
            assert Path(path).exists(), f"Missing: {path}"


def test_profile_substitutes_variables():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(
            main,
            ["init", "--profile", "library"],
            input="mylib\nAlice\n",  # project_name=mylib, author=Alice
        )
        assert result.exit_code == 0, result.output
        golem_toml = Path("golem.toml").read_text()
        assert "mylib" in golem_toml
        assert "Alice" in golem_toml
        assert "{{project_name}}" not in golem_toml
        assert "{{author}}" not in golem_toml


def test_blog_profile_year_substitution():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init", "--profile", "blog"], input="\n\n")
        assert result.exit_code == 0, result.output
        year = str(datetime.date.today().year)
        expected = Path(f"posts/{year}-01-01-hello-world.adoc")
        assert expected.exists(), f"Expected {expected}, not found"


def test_profile_reads_pyproject_toml():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pyproject.toml").write_text(
            '[project]\nname = "mypkg"\nauthors = [{name = "Bob"}]\n',
            encoding="utf-8",
        )
        result = runner.invoke(main, ["init", "--profile", "library"])
        assert result.exit_code == 0, result.output
        golem_toml = Path("golem.toml").read_text()
        assert "mypkg" in golem_toml
        assert "Bob" in golem_toml


def test_unknown_profile_falls_back_to_generic():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init", "--profile", "package"])
        assert result.exit_code == 0, result.output
        assert "Initialization complete" in result.output


def test_template_flag_removed():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init", "--template", "library"])
        assert result.exit_code != 0
        # Click reports "No such option: --template"
        assert "no such option" in result.output.lower() or result.exit_code == 2


def test_init_help_shows_profile():
    runner = CliRunner()
    result = runner.invoke(main, ["init", "--help"])
    assert result.exit_code == 0
    assert "--profile" in result.output
    assert "--template" not in result.output


def test_library_profile_has_api_section():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init", "--profile", "library"], input="\n\n")
        assert result.exit_code == 0, result.output
        golem_toml = Path("golem.toml").read_text()
        assert "[api]" in golem_toml
        assert "packages" in golem_toml
        assert 'output_dir = "api"' in golem_toml
        assert 'output_dir = "docs/api"' not in golem_toml


def test_profile_handles_malformed_pyproject_toml():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pyproject.toml").write_text("invalid toml [[]", encoding="utf-8")
        result = runner.invoke(main, ["init", "--profile", "library"], input="fallback_pkg\nfallback_author\n")
        assert result.exit_code == 0, result.output
        golem_toml = Path("golem.toml").read_text()
        assert "fallback_pkg" in golem_toml
        assert "fallback_author" in golem_toml


def test_profile_handles_non_dict_project_in_pyproject_toml():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pyproject.toml").write_text('project = "not a table"\n', encoding="utf-8")
        result = runner.invoke(main, ["init", "--profile", "library"], input="fallback_pkg\nfallback_author\n")
        assert result.exit_code == 0, result.output
        golem_toml = Path("golem.toml").read_text()
        assert "fallback_pkg" in golem_toml
        assert "fallback_author" in golem_toml


def test_blog_profile_has_rss():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init", "--profile", "blog"], input="\n\n")
        assert result.exit_code == 0, result.output
        golem_toml = Path("golem.toml").read_text()
        assert "rss = true" in golem_toml


def test_cli_profile_adoc_content():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init", "--profile", "cli"], input="\n\n")
        assert result.exit_code == 0, result.output
        content = Path("docs/reference/cli.adoc").read_text()
        assert "== NAME" in content
        assert "== SYNOPSIS" in content
        assert "== OPTIONS" in content


def test_paper_profile_adoc_content():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(main, ["init", "--profile", "paper"], input="\n\n")
        assert result.exit_code == 0, result.output
        content = Path("paper.adoc").read_text()
        assert "[abstract]" in content
        assert "== Introduction" in content
        assert "bibliography::refs.bib[]" in content
