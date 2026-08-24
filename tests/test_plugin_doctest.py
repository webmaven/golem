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
    # NOTE: expected output must NOT start with '['. asciidoctrine's preprocessor
    # mistakes a '['-prefixed line inside a listing block for a block-attribute list,
    # which triggers a PreprocessorWarning about same-length nested verbatim blocks.
    # Use sum() so the output is a plain integer. Filed upstream as a parser bug.
    doc.write_text(
        """= Welcome

[source,python,role="test"]
----
>>> sum(x * 2 for x in [1, 2, 3])
12
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
