"""
= CLI Tests for Golem

This module contains functional tests for verifying that the Click-based command-line interface and its subcommands function correctly.
"""

import click
from click.testing import CliRunner
import pytest
from golem.cli import main, report_engine_diagnostics
from golem.config import GolemConfig
from golem.diagnostics import Diagnostic
from golem.engine import BuildEngine


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "Golem" in result.output


def test_cli_subcommands_exist():
    runner = CliRunner()
    for cmd in ["init", "new", "build", "serve", "plugins", "themes"]:
        result = runner.invoke(main, [cmd, "--help"])
        assert result.exit_code == 0
        assert cmd in result.output or "Show this message and exit" in result.output


def test_cli_build_help_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["build", "--help"])
    assert result.exit_code == 0
    assert "--strict" in result.output
    assert "--verbose" in result.output or "-v" in result.output
    assert "--quiet" in result.output or "-q" in result.output
    assert "--directory" in result.output or "-C" in result.output


def test_cli_serve_help_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--strict" in result.output
    assert "--directory" in result.output or "-C" in result.output


def test_cli_plugins_help_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["plugins", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.output
    assert "--directory" in result.output or "-C" in result.output


def test_cli_themes_help_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["themes", "--help"])
    assert result.exit_code == 0
    assert "--json" in result.output
    assert "--directory" in result.output or "-C" in result.output


def test_report_engine_diagnostics_empty():
    engine = BuildEngine(GolemConfig())
    engine.diagnostics = []
    # Should not raise
    report_engine_diagnostics(engine, strict=True)


def test_report_engine_diagnostics_permissive(capsys):
    engine = BuildEngine(GolemConfig())
    engine.diagnostics = [Diagnostic(file="test.adoc", line=1, column=1, message="Syntax error", severity="error")]
    report_engine_diagnostics(engine, strict=False)
    captured = capsys.readouterr()
    assert "test.adoc:1:1" in captured.err
    assert "Syntax error" in captured.err


def test_report_engine_diagnostics_strict_raises():
    engine = BuildEngine(GolemConfig())
    engine.diagnostics = [Diagnostic(file="test.adoc", line=5, column=2, message="Fatal error", severity="error")]
    with pytest.raises(click.ClickException) as excinfo:
        report_engine_diagnostics(engine, strict=True)
    assert "Compilation failed due to build diagnostics in strict mode." in str(excinfo.value)


def test_report_engine_diagnostics_strict_warnings_only(capsys):
    engine = BuildEngine(GolemConfig())
    engine.diagnostics = [Diagnostic(file="test.adoc", line=3, column=1, message="Warning msg", severity="warning")]
    # Warnings only in strict mode should not raise
    report_engine_diagnostics(engine, strict=True)
    captured = capsys.readouterr()
    assert "test.adoc:3:1" in captured.err
