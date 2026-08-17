"""
= CLI Tests for Golem

This module contains functional tests for verifying that the Click-based command-line interface and its subcommands function correctly.
"""

from click.testing import CliRunner
from golem.cli import main


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "Golem" in result.output


def test_cli_subcommands_exist():
    runner = CliRunner()
    for cmd in ["init", "new", "build", "serve"]:
        result = runner.invoke(main, [cmd, "--help"])
        assert result.exit_code == 0
        assert cmd in result.output or "Show this message and exit" in result.output


def test_cli_build_help_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["build", "--help"])
    assert result.exit_code == 0
    assert "--strict" in result.output
    assert "--verbose" in result.output or "-v" in result.output
    assert "--directory" in result.output or "-C" in result.output


def test_cli_serve_help_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--strict" in result.output
    assert "--directory" in result.output or "-C" in result.output
