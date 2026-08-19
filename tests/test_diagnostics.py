"""
= Diagnostics & CLI Enhancement Tests for Golem

This module contains unit and integration tests for:
- Formatted compiler diagnostics (source coordinates and context snippets)
- CLI --strict flag and permissive fallback behavior
- CLI -v / --verbose flag
- CLI -C / --directory flag on init, build, and serve
- Server errors_func integration
"""

from pathlib import Path
from click.testing import CliRunner
from golem.cli import main, format_diagnostic
import asciidoctrine


def test_format_diagnostic_with_coordinates_and_context(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    doc_file = docs_dir / "02-architecture.adoc"

    # Create 14-line file
    lines = [
        "= System Documentation",
        "Author Name",
        "",
        "Intro paragraph here.",
        "",
        "Line 6 content",
        "Line 7 content",
        "Line 8 content",
        "Line 9 content",
        "Line 10 content",
        "Line 11 content",
        "= Architecture",
        "",
        "[source,python",
    ]
    doc_file.write_text("\n".join(lines), encoding="utf-8")

    err = {
        "file": str(doc_file),
        "line": 14,
        "column": 5,
        "message": "Unclosed attribute list",
    }

    formatted = format_diagnostic(err)
    assert f"Error in {doc_file}:14:5" in formatted
    assert "12 | = Architecture" in formatted
    assert "13 |" in formatted
    assert "14 | [source,python" in formatted
    assert "^-- Unclosed attribute list" in formatted


def test_format_diagnostic_first_line_of_file(tmp_path):
    doc_file = tmp_path / "index.adoc"
    doc_file.write_text("= Broken Header", encoding="utf-8")

    err = {
        "file": str(doc_file),
        "line": 1,
        "column": 3,
        "message": "Invalid header syntax",
    }

    formatted = format_diagnostic(err)
    assert f"Error in {doc_file}:1:3" in formatted
    assert "1 | = Broken Header" in formatted
    assert "  |   ^-- Invalid header syntax" in formatted


def test_format_diagnostic_missing_file_fallback():
    err = {
        "file": "missing/file.adoc",
        "line": 5,
        "column": 2,
        "message": "File not found",
    }
    formatted = format_diagnostic(err)
    assert "Error in missing/file.adoc:5:2" in formatted
    assert "File not found" in formatted


def test_format_diagnostic_from_exception():
    class SyntaxException(Exception):
        def __init__(self, msg, line, column):
            super().__init__(msg)
            self.line = line
            self.column = column

    exc = SyntaxException("Unexpected token", line=10, column=4)
    err = {
        "file": "test.adoc",
        "exception": exc,
        "message": str(exc),
    }
    formatted = format_diagnostic(err)
    assert "Error in test.adoc:10:4" in formatted
    assert "Unexpected token" in formatted


def test_cli_build_permissive_mode_emits_diagnostics_and_continues(tmp_path, monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        # Valid page
        content_dir = Path("content")
        (content_dir / "valid.adoc").write_text("= Valid Page\n\nAll good here.", encoding="utf-8")

        # Broken page
        (content_dir / "broken.adoc").write_text("= Broken Page\n\n[broken_syntax", encoding="utf-8")

        orig_parse = asciidoctrine.parse_to_ast

        def mock_parse(text, base_dir=None):
            if "[broken_syntax" in text:
                err = ValueError("Unclosed block macro delimiter")
                err.line = 3  # type: ignore[attr-defined]
                err.column = 1  # type: ignore[attr-defined]
                raise err
            return orig_parse(text, base_dir=base_dir)

        monkeypatch.setattr(asciidoctrine, "parse_to_ast", mock_parse)

        res = runner.invoke(main, ["build"])
        assert res.exit_code == 0
        # Valid pages are built
        assert Path("dist/valid.html").exists()
        assert Path("dist/index.html").exists()
        # Diagnostics are emitted in the CLI output
        assert "Error in " in res.output
        assert "broken.adoc" in res.output
        assert "Unclosed block macro delimiter" in res.output
        assert "Compilation finished. Built 2 pages." in res.output


def test_cli_build_strict_flag_fails_on_error(tmp_path, monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        content_dir = Path("content")
        (content_dir / "broken.adoc").write_text("= Broken Page\n\n[broken_syntax", encoding="utf-8")

        orig_parse = asciidoctrine.parse_to_ast

        def mock_parse(text, base_dir=None):
            if "[broken_syntax" in text:
                err = ValueError("Unclosed block macro delimiter")
                err.line = 3  # type: ignore[attr-defined]
                err.column = 1  # type: ignore[attr-defined]
                raise err
            return orig_parse(text, base_dir=base_dir)

        monkeypatch.setattr(asciidoctrine, "parse_to_ast", mock_parse)

        res = runner.invoke(main, ["build", "--strict"])
        assert res.exit_code != 0
        assert "Compilation Error" in res.output
        assert "broken.adoc" in res.output


def test_cli_build_strict_config_fails_on_error(tmp_path, monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        # Configure strict mode in golem.toml
        golem_toml = Path("golem.toml")
        golem_toml.write_text(
            """
[site]
title = "Strict Site"

[build]
content_dir = "content"
output_dir = "dist"
strict = true
""",
            encoding="utf-8",
        )

        content_dir = Path("content")
        (content_dir / "broken.adoc").write_text("= Broken Page\n\n[broken_syntax", encoding="utf-8")

        def mock_parse(text, base_dir=None):
            if "[broken_syntax" in text:
                raise ValueError("Fatal syntax error")
            return asciidoctrine.parse_to_ast(text, base_dir=base_dir)

        monkeypatch.setattr(asciidoctrine, "parse_to_ast", mock_parse)

        res = runner.invoke(main, ["build"])
        assert res.exit_code != 0
        assert "Compilation Error" in res.output


def test_cli_build_verbose_flag(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        res_short = runner.invoke(main, ["build", "-v"])
        assert res_short.exit_code == 0
        assert "Building static site..." in res_short.output

        res_long = runner.invoke(main, ["build", "--verbose"])
        assert res_long.exit_code == 0
        assert "Building static site..." in res_long.output


def test_cli_directory_flag_build(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        proj_dir = Path("my_project")
        proj_dir.mkdir()

        # Init inside subfolder
        res_init = runner.invoke(main, ["init", "-C", "my_project"])
        assert res_init.exit_code == 0
        assert (proj_dir / "golem.toml").exists()
        assert (proj_dir / "content" / "index.adoc").exists()

        # Build from outside using -C
        res_build = runner.invoke(main, ["build", "-C", "my_project"])
        assert res_build.exit_code == 0
        assert (proj_dir / "dist" / "index.html").exists()

        # Build using --directory
        res_build_dir = runner.invoke(main, ["build", "--directory", "my_project", "--clean"])
        assert res_build_dir.exit_code == 0
        assert (proj_dir / "dist" / "index.html").exists()


def test_cli_directory_flag_init(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        res = runner.invoke(main, ["init", "-C", "nested/site"])
        assert res.exit_code == 0
        assert Path("nested/site/golem.toml").exists()
        assert Path("nested/site/content/index.adoc").exists()


def test_cli_serve_passes_errors_func_and_directory(tmp_path, monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])

        passed_kwargs = {}

        class MockLiveReloadServer:
            def __init__(self, **kwargs):
                passed_kwargs.update(kwargs)

            def run(self):
                pass

        monkeypatch.setattr("golem.server.LiveReloadServer", MockLiveReloadServer)

        res = runner.invoke(main, ["serve"])
        assert res.exit_code == 0
        assert "errors_func" in passed_kwargs
        assert callable(passed_kwargs["errors_func"])


def test_cli_serve_strict_fails_on_compilation_error(tmp_path, monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])
        content_dir = Path("content")
        (content_dir / "broken.adoc").write_text("= Broken\n\n[broken", encoding="utf-8")

        def mock_parse(text, base_dir=None):
            if "[broken" in text:
                raise ValueError("Fatal parse error")
            return asciidoctrine.parse_to_ast(text, base_dir=base_dir)

        monkeypatch.setattr(asciidoctrine, "parse_to_ast", mock_parse)

        res = runner.invoke(main, ["serve", "--strict"])
        assert res.exit_code != 0
        assert "Compilation Error" in res.output


def test_cli_serve_permissive_emits_diagnostics_and_runs(tmp_path, monkeypatch):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(main, ["init"])
        content_dir = Path("content")
        (content_dir / "broken.adoc").write_text("= Broken\n\n[broken", encoding="utf-8")

        def mock_parse(text, base_dir=None):
            if "[broken" in text:
                raise ValueError("Syntax warning intercepted")
            return asciidoctrine.parse_to_ast(text, base_dir=base_dir)

        monkeypatch.setattr(asciidoctrine, "parse_to_ast", mock_parse)

        class MockLiveReloadServer:
            def __init__(self, **kwargs):
                pass

            def run(self):
                pass

        monkeypatch.setattr("golem.server.LiveReloadServer", MockLiveReloadServer)

        res = runner.invoke(main, ["serve"])
        assert res.exit_code == 0
        assert "Error in " in res.output
        assert "Syntax warning intercepted" in res.output


def test_format_diagnostic_regex_extraction_from_message():
    err = {
        "file": "manual.adoc",
        "message": "Syntax issue at line 25, column 12: invalid macro",
    }
    formatted = format_diagnostic(err)
    assert "Error in manual.adoc:25:12" in formatted
    assert "invalid macro" in formatted


def test_format_diagnostic_three_digit_line_numbers(tmp_path):
    doc_file = tmp_path / "long_doc.adoc"
    lines = [f"Line {i}" for i in range(1, 105)]
    lines[99] = "= Section 100"
    lines[100] = ""
    lines[101] = "Invalid [token"
    doc_file.write_text("\n".join(lines), encoding="utf-8")

    err = {
        "file": str(doc_file),
        "line": 102,
        "column": 9,
        "message": "Unclosed token bracket",
    }
    formatted = format_diagnostic(err)
    assert f"Error in {doc_file}:102:9" in formatted
    assert "100 | = Section 100" in formatted
    assert "101 |" in formatted
    assert "102 | Invalid [token" in formatted
    assert "^-- Unclosed token bracket" in formatted
