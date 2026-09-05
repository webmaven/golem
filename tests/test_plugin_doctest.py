from __future__ import annotations

from pathlib import Path
import click
from click.testing import CliRunner

from golem.plugins import get_plugin_manager


def test_doctest_plugin_registration():
    from golem.plugins import doctest

    pm = get_plugin_manager()
    pm.register(doctest)
    assert pm.is_registered(doctest)


def test_run_adoc_file_passing(tmp_path: Path):
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "passing.adoc"
    doc.write_text(
        """= Passing Guide

[source,python,role="test"]
----
>>> 2 + 2
4
>>> 'hello'.upper()
'HELLO'
----
""",
        encoding="utf-8",
    )

    passed, failed, errors = run_adoc_file(doc)
    assert passed == 1
    assert failed == 0
    assert len(errors) == 0


def test_run_adoc_file_failing(tmp_path: Path):
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "failing.adoc"
    doc.write_text(
        """= Failing Guide

[source,python,role="test"]
----
>>> 2 + 2
5
----
""",
        encoding="utf-8",
    )

    passed, failed, errors = run_adoc_file(doc)
    assert passed == 0
    assert failed == 1
    assert len(errors) == 1
    assert "Expected:\n    5\nGot:\n    4" in errors[0] or "5" in errors[0]


def test_run_adoc_file_shared_context_and_reset(tmp_path: Path):
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "shared.adoc"
    doc.write_text(
        """= Shared Context Guide

[source,python,role="shared"]
----
x = 100
----

[source,python,role="shared test"]
----
>>> x + 50
150
----

[source,python,role="reset"]
----
pass
----

[source,python,role="shared test"]
----
>>> 'x' in dir()
False
----
""",
        encoding="utf-8",
    )

    passed, failed, errors = run_adoc_file(doc)
    assert errors == []
    assert passed >= 2
    assert failed == 0


def test_run_adoc_file_eager_mode(tmp_path: Path):
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "eager.adoc"
    doc.write_text(
        """= Eager Guide

[source,python]
----
>>> 10 * 10
100
----
""",
        encoding="utf-8",
    )

    # In explicit mode, unmarked block is skipped
    passed, failed, errors = run_adoc_file(doc, mode="explicit")
    assert passed == 0
    assert failed == 0

    # In eager mode, unmarked block is executed
    passed, failed, errors = run_adoc_file(doc, mode="eager")
    assert passed == 1
    assert failed == 0


def test_run_adoc_file_split_sections(tmp_path: Path):
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "multi_section.adoc"
    doc.write_text(
        """= Document Title

== Section One

[source,python,role="test"]
----
>>> a = 1
>>> a + 1
2
----

== Section Two

[source,python,role="test"]
----
>>> b = 10
>>> b * 2
20
----
""",
        encoding="utf-8",
    )

    passed, failed, errors = run_adoc_file(doc, split_sections=True)
    assert passed == 2
    assert failed == 0


def test_run_adoc_file_split_sections_partial_failure(tmp_path: Path):
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "partial_fail.adoc"
    doc.write_text(
        """= Document Title

== Section One

[source,python,role="test"]
----
>>> 1 + 1
2
----

== Section Two

[source,python,role="test"]
----
>>> 1 + 1
999
----
""",
        encoding="utf-8",
    )

    # Without split_sections: failure in section two aborts, passed=0, failed=1
    passed, failed, errors = run_adoc_file(doc, split_sections=False)
    assert passed == 0
    assert failed == 1
    assert len(errors) == 1

    # With split_sections: section one passes (1), section two fails (1)
    passed, failed, errors = run_adoc_file(doc, split_sections=True)
    assert passed == 1
    assert failed == 1
    assert len(errors) == 1


def test_run_path_split_sections(tmp_path: Path):
    from golem.plugins.doctest.runner import run_path

    doc = tmp_path / "multi_section.adoc"
    doc.write_text(
        """= Document Title

== Section One

[source,python,role="test"]
----
>>> 10 + 20
30
----

== Section Two

[source,python,role="test"]
----
>>> 5 * 5
25
----
""",
        encoding="utf-8",
    )

    passed, failed, errors = run_path(doc, split_sections=True)
    assert passed == 2
    assert failed == 0

    dir_path = tmp_path / "docs"
    dir_path.mkdir()
    (dir_path / "doc.adoc").write_text(
        """= Doc

== Section A

[source,python,role="test"]
----
>>> 'hello'.title()
'Hello'
----
""",
        encoding="utf-8",
    )
    passed, failed, errors = run_path(dir_path, split_sections=True)
    assert passed == 1
    assert failed == 0


def test_run_all_and_run_doctests_split_sections(tmp_path: Path):
    from golem.plugins.doctest import run_doctests
    from golem.plugins.doctest.runner import run_all

    doc = tmp_path / "multi_section.adoc"
    doc.write_text(
        """= Document Title

== Section One

[source,python,role="test"]
----
>>> 2 * 10
20
----

== Section Two

[source,python,role="test"]
----
>>> 3 * 10
30
----
""",
        encoding="utf-8",
    )

    exit_code = run_all(paths=[doc], split_sections=True)
    assert exit_code == 0

    exit_code = run_doctests(paths=[doc], split_sections=True)
    assert exit_code == 0


def test_cli_subcommand_split_sections(tmp_path: Path):
    from golem.plugins import doctest

    doc = tmp_path / "multi_section.adoc"
    doc.write_text(
        """= Title

== Section One

[source,python,role="test"]
----
>>> 3 * 3
9
----

== Section Two

[source,python,role="test"]
----
>>> 4 * 4
16
----
""",
        encoding="utf-8",
    )

    @click.group()
    def cli():
        pass

    doctest.golem_add_subcommands(cli)

    runner = CliRunner()
    result = runner.invoke(cli, ["doctest", "--split-sections", str(doc)])
    assert result.exit_code == 0


def test_run_docstring_tests_passing(tmp_path: Path):
    from golem.plugins.doctest.runner import run_docstring_tests

    py_file = tmp_path / "calc.py"
    py_file.write_text(
        '''"""Math utilities."""

def square(n: int) -> int:
    """
    = square

    [source,python,role="test"]
    ----
    >>> square(4)
    16
    ----
    """
    return n * n
''',
        encoding="utf-8",
    )

    passed, failed, errors = run_docstring_tests(py_file)
    assert passed == 1
    assert failed == 0
    assert len(errors) == 0


def test_run_docstring_tests_failing(tmp_path: Path):
    from golem.plugins.doctest.runner import run_docstring_tests

    py_file = tmp_path / "broken.py"
    py_file.write_text(
        '''"""Broken utilities."""

def bad_cube(n: int) -> int:
    """
    = bad_cube

    [source,python,role="test"]
    ----
    >>> bad_cube(3)
    999
    ----
    """
    return n * n * n
''',
        encoding="utf-8",
    )

    passed, failed, errors = run_docstring_tests(py_file)
    assert failed == 1
    assert len(errors) == 1
    assert "bad_cube" in errors[0]


def test_run_path_directory(tmp_path: Path):
    from golem.plugins.doctest.runner import run_path

    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    (docs_dir / "guide1.adoc").write_text(
        """= Guide 1

[source,python,role="test"]
----
>>> 1 + 1
2
----
""",
        encoding="utf-8",
    )

    (docs_dir / "guide2.adoc").write_text(
        """= Guide 2

[source,python,role="test"]
----
>>> 3 * 3
9
----
""",
        encoding="utf-8",
    )

    passed, failed, errors = run_path(docs_dir)
    assert passed == 2
    assert failed == 0
    assert len(errors) == 0


def test_run_all_and_run_doctests(tmp_path: Path):
    from golem.plugins.doctest import run_doctests
    from golem.plugins.doctest.runner import run_all

    doc_pass = tmp_path / "pass.adoc"
    doc_pass.write_text(
        """= Pass

[source,python,role="test"]
----
>>> 'a' + 'b'
'ab'
----
""",
        encoding="utf-8",
    )

    code = run_all(paths=[doc_pass])
    assert code == 0

    doc_fail = tmp_path / "fail.adoc"
    doc_fail.write_text(
        """= Fail

[source,python,role="test"]
----
>>> 1 / 0
----
""",
        encoding="utf-8",
    )

    code_fail = run_all(paths=[doc_fail])
    assert code_fail == 1

    # Programmatic run_doctests
    assert run_doctests(paths=[doc_pass]) == 0
    assert run_doctests(paths=[doc_fail]) == 1


def test_cli_subcommand_doctest_passing(tmp_path: Path):
    from golem.plugins import doctest

    doc = tmp_path / "index.adoc"
    doc.write_text(
        """= Welcome

[source,python,role="test"]
----
>>> [x * 2 for x in [1, 2, 3]]
[2, 4, 6]
----
""",
        encoding="utf-8",
    )

    @click.group()
    def cli():
        pass

    doctest.golem_add_subcommands(cli)

    runner = CliRunner()
    result = runner.invoke(cli, ["doctest", str(doc)])
    assert result.exit_code == 0
    assert "passed" in result.output.lower() or result.exit_code == 0


def test_cli_subcommand_doctest_failing(tmp_path: Path):
    from golem.plugins import doctest

    doc = tmp_path / "fail.adoc"
    doc.write_text(
        """= Failure

[source,python,role="test"]
----
>>> 10 == 20
True
----
""",
        encoding="utf-8",
    )

    @click.group()
    def cli():
        pass

    doctest.golem_add_subcommands(cli)

    runner = CliRunner()
    result = runner.invoke(cli, ["doctest", str(doc)])
    assert result.exit_code == 1


def test_cli_subcommand_verbose(tmp_path: Path):
    from golem.plugins import doctest

    doc = tmp_path / "sample.adoc"
    doc.write_text(
        """= Sample

[source,python,role="test"]
----
>>> 1 + 1
2
----
""",
        encoding="utf-8",
    )

    @click.group()
    def cli():
        pass

    doctest.golem_add_subcommands(cli)

    runner = CliRunner()
    result = runner.invoke(cli, ["doctest", "-v", str(doc)])
    assert result.exit_code == 0
    assert "PASS" in result.output or "sample.adoc" in result.output or "passed" in result.output


def test_cli_subcommand_source_docstring(tmp_path: Path):
    from golem.plugins import doctest

    py_file = tmp_path / "mypkg.py"
    py_file.write_text(
        '''"""Docstrings."""

def greet(name: str) -> str:
    """
    = greet

    [source,python,role="test"]
    ----
    >>> greet('World')
    'Hello, World!'
    ----
    """
    return f"Hello, {name}!"
''',
        encoding="utf-8",
    )

    @click.group()
    def cli():
        pass

    doctest.golem_add_subcommands(cli)

    runner = CliRunner()
    result = runner.invoke(cli, ["doctest", "-s", str(py_file)])
    assert result.exit_code == 0


def test_cli_subcommand_fail_fast(tmp_path: Path):
    from golem.plugins.doctest.runner import run_path

    docs_dir = tmp_path / "fast_docs"
    docs_dir.mkdir()

    (docs_dir / "01_fail.adoc").write_text(
        """= Fail 1

[source,python,role="test"]
----
>>> 1 == 2
True
----
""",
        encoding="utf-8",
    )

    (docs_dir / "02_pass.adoc").write_text(
        """= Pass 2

[source,python,role="test"]
----
>>> 2 == 2
True
----
""",
        encoding="utf-8",
    )

    passed, failed, errors = run_path(docs_dir, fail_fast=True)
    assert failed >= 1
    # Because of fail-fast, 02_pass should not have been executed or total executed is reduced
    assert passed == 0


def test_run_doctests_auto_discovery_with_config(tmp_path: Path, monkeypatch):
    """Verify run_doctests() auto-discovers content_dir from golem.yaml config."""
    from golem.plugins.doctest import run_asciidoc_doctests, run_doctests

    monkeypatch.chdir(tmp_path)
    content_dir = tmp_path / "custom_content"
    content_dir.mkdir()
    (content_dir / "doc.adoc").write_text(
        """= Custom Guide

[source,python,role="test"]
----
>>> 10 + 5
15
----
""",
        encoding="utf-8",
    )
    config_file = tmp_path / "golem.toml"
    config_file.write_text('[build]\ncontent_dir = "custom_content"\n', encoding="utf-8")

    assert run_doctests() == 0
    assert run_asciidoc_doctests() == 0


def test_run_doctests_auto_discovery_docs_dir(tmp_path: Path, monkeypatch):
    """Verify run_doctests() falls back to docs/ directory when no config is present."""
    from golem.plugins.doctest import run_doctests

    monkeypatch.chdir(tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.adoc").write_text(
        """= Docs Guide

[source,python,role="test"]
----
>>> 3 * 7
21
----
""",
        encoding="utf-8",
    )

    assert run_doctests() == 0


def test_run_doctests_auto_discovery_no_docs_fallback(tmp_path: Path, monkeypatch):
    """Verify run_doctests() falls back to Path('docs') when neither config nor docs exists."""
    from golem.plugins.doctest import run_doctests

    monkeypatch.chdir(tmp_path)
    # Neither config nor docs exists
    result = run_doctests()
    assert result == 0


def test_run_adoc_file_nonexistent(tmp_path: Path):
    """Verify run_adoc_file handles non-existent file gracefully."""
    from golem.plugins.doctest.runner import run_adoc_file

    missing = tmp_path / "missing.adoc"
    passed, failed, errors = run_adoc_file(missing)
    assert passed == 0
    assert failed == 1
    assert any("File not found" in err for err in errors)


def test_run_adoc_file_read_error(tmp_path: Path, monkeypatch):
    """Verify run_adoc_file captures read error exceptions."""
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "unreadable.adoc"
    doc.write_text("= Title\n", encoding="utf-8")

    def broken_read_text(*args, **kwargs):
        raise OSError("Permission denied simulation")

    monkeypatch.setattr(Path, "read_text", broken_read_text)
    passed, failed, errors = run_adoc_file(doc)
    assert passed == 0
    assert failed == 1
    assert any("Failed to read" in err for err in errors)


def test_run_adoc_file_parse_error(tmp_path: Path, monkeypatch):
    """Verify run_adoc_file captures parse error exceptions."""
    import golem.plugins.doctest.runner as doctest_runner
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "bad_parse.adoc"
    doc.write_text("= Title\n", encoding="utf-8")

    def broken_parse(*args, **kwargs):
        raise ValueError("Simulated parse error")

    monkeypatch.setattr(doctest_runner, "parse_adoc_tests", broken_parse)
    passed, failed, errors = run_adoc_file(doc)
    assert passed == 0
    assert failed == 1
    assert any("AsciiDoc parse error" in err for err in errors)


def test_run_adoc_file_unexpected_runtime_error(tmp_path: Path, monkeypatch):
    """Verify run_adoc_file captures unexpected runtime errors during execution."""
    import golem.plugins.doctest.runner as doctest_runner
    from golem.plugins.doctest.runner import run_adoc_file

    doc = tmp_path / "runtime_err.adoc"
    doc.write_text(
        """= Test
[source,python,role="test"]
----
>>> 1 + 1
2
----
""",
        encoding="utf-8",
    )

    def broken_run_blocks(*args, **kwargs):
        raise TypeError("Simulated unexpected runner crash")

    monkeypatch.setattr(doctest_runner, "run_test_blocks", broken_run_blocks)
    passed, failed, errors = run_adoc_file(doc)
    assert passed == 0
    assert failed == 1
    assert any("Unexpected error" in err for err in errors)


def test_run_docstring_tests_unexpected_error(tmp_path: Path, monkeypatch):
    """Verify run_docstring_tests captures extraction exceptions."""
    import golem.plugins.doctest.runner as doctest_runner
    from golem.plugins.doctest.runner import run_docstring_tests

    py_file = tmp_path / "error_mod.py"
    py_file.write_text("# code\n", encoding="utf-8")

    def broken_extract(*args, **kwargs):
        raise RuntimeError("Extraction failed completely")

    monkeypatch.setattr(doctest_runner, "extract_and_run_docstring_tests", broken_extract)
    passed, failed, errors = run_docstring_tests(py_file)
    assert passed == 0
    assert failed == 1
    assert any("Error extracting docstring tests" in err for err in errors)


def test_run_path_nonexistent(tmp_path: Path):
    """Verify run_path returns error when target path does not exist."""
    from golem.plugins.doctest.runner import run_path

    missing = tmp_path / "no_such_path"
    passed, failed, errors = run_path(missing)
    assert passed == 0
    assert failed == 1
    assert any("Path not found" in err for err in errors)


def test_run_all_verbose_output(tmp_path: Path, capsys):
    """Verify run_all verbose formatting for skipped, passed, and failed tests."""
    from golem.plugins.doctest.runner import run_all

    empty_doc = tmp_path / "empty.adoc"
    empty_doc.write_text("= No Code Blocks Here\n", encoding="utf-8")

    pass_doc = tmp_path / "pass.adoc"
    pass_doc.write_text(
        """= Pass
[source,python,role="test"]
----
>>> 5 * 5
25
----
""",
        encoding="utf-8",
    )

    fail_doc = tmp_path / "fail.adoc"
    fail_doc.write_text(
        """= Fail
[source,python,role="test"]
----
>>> 1 == 2
True
----
""",
        encoding="utf-8",
    )

    exit_code = run_all(paths=[empty_doc, pass_doc, fail_doc], verbose=True)
    assert exit_code == 1

    captured = capsys.readouterr()
    assert "SKIP:" in captured.out
    assert "PASS:" in captured.out
    assert "FAIL:" in captured.out
    assert "Doctest Summary:" in captured.out


def test_run_all_source_verbose_and_fail_fast(tmp_path: Path, capsys):
    """Verify run_all verbose and fail_fast output when executing source docstring tests."""
    from golem.plugins.doctest.runner import run_all

    py_file_pass = tmp_path / "good.py"
    py_file_pass.write_text(
        '''"""Good."""
def add(a: int, b: int) -> int:
    """
    = add
    [source,python,role="test"]
    ----
    >>> add(1, 2)
    3
    ----
    """
    return a + b
''',
        encoding="utf-8",
    )

    py_file_fail = tmp_path / "bad.py"
    py_file_fail.write_text(
        '''"""Bad."""
def broken() -> int:
    """
    = broken
    [source,python,role="test"]
    ----
    >>> broken()
    100
    ----
    """
    return 0
''',
        encoding="utf-8",
    )

    # Test passing source with verbose
    code_pass = run_all(source=str(py_file_pass), verbose=True)
    assert code_pass == 0
    captured_pass = capsys.readouterr()
    assert "PASS: Docstring tests for" in captured_pass.out

    # Test failing source with fail_fast and verbose
    code_fail = run_all(source=str(py_file_fail), verbose=True, fail_fast=True)
    assert code_fail == 1
    captured_fail = capsys.readouterr()
    assert "FAIL: Docstring tests for" in captured_fail.out


def test_run_asciidoc_doctests_auto_discovery_config(tmp_path: Path, monkeypatch):
    """Verify run_asciidoc_doctests auto-discovers content_dir from golem.toml."""
    from golem.plugins.doctest import run_asciidoc_doctests

    monkeypatch.chdir(tmp_path)
    content_dir = tmp_path / "custom_docs"
    content_dir.mkdir()
    doc_file = content_dir / "guide.adoc"
    doc_file.write_text(
        """= Guide
[source,python,role="test"]
----
>>> 10 * 10
100
----
""",
        encoding="utf-8",
    )

    config_file = tmp_path / "golem.toml"
    config_file.write_text('[build]\ncontent_dir = "custom_docs"\n', encoding="utf-8")

    result = run_asciidoc_doctests()
    assert result == 0


def test_run_asciidoc_doctests_auto_discovery_docs_fallback(tmp_path: Path, monkeypatch):
    """Verify run_asciidoc_doctests falls back to docs directory when no config exists."""
    from golem.plugins.doctest import run_asciidoc_doctests

    monkeypatch.chdir(tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    doc_file = docs_dir / "quickstart.adoc"
    doc_file.write_text(
        """= Quickstart
[source,python,role="test"]
----
>>> 'a' + 'b'
'ab'
----
""",
        encoding="utf-8",
    )

    result = run_asciidoc_doctests()
    assert result == 0


def test_runner_uses_toplevel_asciidoctest_imports():
    """Verify runner.py uses top-level PEP 561 public imports from asciidoctest."""
    import ast
    import golem.plugins.doctest.runner as runner_mod

    runner_src = Path(runner_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(runner_src)
    imports_from_asciidoctest = [
        node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == "asciidoctest"
    ]
    imported_names = {alias.name for node in imports_from_asciidoctest for alias in node.names}
    assert "AsciiDocTestFailure" in imported_names
    assert "extract_and_run_docstring_tests" in imported_names

    submodule_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module in ("asciidoctest.docstring_extractor", "asciidoctest.runner")
    ]
    submodule_names = {alias.name for node in submodule_imports for alias in node.names}
    assert "extract_and_run_docstring_tests" not in submodule_names
    assert "AsciiDocTestFailure" not in submodule_names


def test_run_docstring_tests_nested_classes_and_methods_passing(tmp_path: Path):
    """Verify docstring doctest execution with nested classes, inner methods, and classmethods."""
    from golem.plugins.doctest.runner import run_docstring_tests

    py_file = tmp_path / "nested_structure.py"
    py_file.write_text(
        '''"""Module docstring.

[source,python,role="test"]
----
>>> MODULE_CONST = 100
>>> MODULE_CONST
100
----
"""

class Parent:
    """Parent class docstring.

    [source,python,role="test"]
    ----
    >>> p = Parent("alice")
    >>> p.name
    'alice'
    ----
    """

    def __init__(self, name: str):
        self.name = name

    def compute(self, x: int) -> int:
        """Parent method docstring.

        [source,python,role="test"]
        ----
        >>> Parent('test').compute(5)
        10
        ----
        """
        return x * 2

    class Child:
        """Nested child class docstring.

        [source,python,role="test"]
        ----
        >>> c = Parent.Child()
        >>> c.describe()
        'child instance'
        ----
        """

        def describe(self) -> str:
            """Child method docstring.

            [source,python,role="test"]
            ----
            >>> Parent.Child().describe()
            'child instance'
            ----
            """
            return "child instance"

        class GrandChild:
            """Deeply nested grandchild class docstring.

            [source,python,role="test"]
            ----
            >>> gc = Parent.Child.GrandChild()
            >>> gc.level
            3
            ----
            """
            level = 3
''',
        encoding="utf-8",
    )

    passed, failed, errors = run_docstring_tests(py_file)
    assert passed == 6
    assert failed == 0
    assert len(errors) == 0


def test_run_docstring_tests_nested_classes_and_methods_failing(tmp_path: Path):
    """Verify docstring doctest execution captures failures in nested methods with proper scope naming."""
    from golem.plugins.doctest.runner import run_docstring_tests

    py_file = tmp_path / "failing_nested.py"
    py_file.write_text(
        '''"""Module."""

class Container:
    """Container."""

    class NestedWorker:
        """NestedWorker."""

        def process(self) -> int:
            """Process method.

            [source,python,role="test"]
            ----
            >>> 10 + 20
            999
            ----
            """
            return 30
''',
        encoding="utf-8",
    )

    passed, failed, errors = run_docstring_tests(py_file)
    assert passed == 0
    assert failed == 1
    assert len(errors) == 1
    assert "Container.NestedWorker.process" in errors[0]
