from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import click

from asciidoctest.docstring_extractor import extract_and_run_docstring_tests
from asciidoctest.parser import parse_adoc_tests
from asciidoctest.runner import AsciiDocTestFailure, run_test_blocks


def run_adoc_file(path: Path | str, mode: str = "explicit") -> tuple[int, int, list[str]]:
    """Execute AsciiDoc doctest blocks extracted from a single .adoc file.

    Returns:
        tuple[int, int, list[str]]: (passed_count, failed_count, error_messages)
    """
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return 0, 1, [f"File not found: {file_path}"]

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return 0, 1, [f"Failed to read {file_path}: {e}"]

    try:
        blocks = parse_adoc_tests(content, mode=mode)
    except Exception as e:
        return 0, 1, [f"[{file_path}] AsciiDoc parse error: {e}"]

    if not blocks:
        return 0, 0, []

    shared_globals: dict[str, Any] = {"__file__": str(file_path.resolve()), "__name__": "__main__"}
    try:
        run_test_blocks(blocks, shared_globals)
        return len(blocks), 0, []
    except AsciiDocTestFailure as e:
        return 0, 1, [f"[{file_path}] {e}"]
    except Exception as e:
        return 0, 1, [f"[{file_path}] Unexpected error: {e}"]


def run_docstring_tests(source_target: Path | str, mode: str = "explicit") -> tuple[int, int, list[str]]:
    """Extract and execute AsciiDoc docstring tests from a Python file, directory, or module.

    Returns:
        tuple[int, int, list[str]]: (passed_count, failed_count, error_messages)
    """
    try:
        stats = extract_and_run_docstring_tests(source_target, mode=mode)
        passed = stats.get("passed", 0)
        failed = stats.get("failed", 0)
        return passed, failed, []
    except AsciiDocTestFailure as e:
        return 0, 1, [str(e)]
    except Exception as e:
        return 0, 1, [f"Error extracting docstring tests from {source_target}: {e}"]


def run_path(path: Path | str, mode: str = "explicit", fail_fast: bool = False) -> tuple[int, int, list[str]]:
    """Execute AsciiDoc doctests for a single file or recursively for a directory.

    Returns:
        tuple[int, int, list[str]]: (passed_count, failed_count, error_messages)
    """
    target = Path(path)
    if not target.exists():
        return 0, 1, [f"Path not found: {target}"]

    if target.is_file():
        if target.suffix == ".py":
            return run_docstring_tests(target, mode=mode)
        return run_adoc_file(target, mode=mode)

    if target.is_dir():
        adoc_files = sorted(set(list(target.rglob("*.adoc")) + list(target.rglob("*.asciidoc"))))
        total_passed = 0
        total_failed = 0
        all_errors: list[str] = []

        for adoc_file in adoc_files:
            passed, failed, errors = run_adoc_file(adoc_file, mode=mode)
            total_passed += passed
            total_failed += failed
            all_errors.extend(errors)
            if fail_fast and failed > 0:
                break

        return total_passed, total_failed, all_errors

    return 0, 0, []


def run_all(
    paths: Sequence[Path | str] | None = None,
    source: str | None = None,
    mode: str = "explicit",
    verbose: bool = False,
    fail_fast: bool = False,
) -> int:
    """Run all specified test paths and/or Python source targets.

    Returns:
        int: 0 if all tests passed, 1 if any failure occurred.
    """
    total_passed = 0
    total_failed = 0
    all_errors: list[str] = []

    if source:
        passed, failed, errors = run_docstring_tests(source, mode=mode)
        total_passed += passed
        total_failed += failed
        all_errors.extend(errors)
        if verbose:
            if failed == 0:
                click.echo(f"PASS: Docstring tests for '{source}' ({passed} test(s))")
            else:
                click.echo(f"FAIL: Docstring tests for '{source}'")
        if fail_fast and failed > 0:
            for err in all_errors:
                click.echo(err, err=True)
            click.echo(f"Doctest Summary: {total_passed} passed, {total_failed} failed")
            return 1

    if paths:
        for path in paths:
            p_path = Path(path)
            if p_path.is_file():
                if p_path.suffix == ".py":
                    passed, failed, errors = run_docstring_tests(p_path, mode=mode)
                else:
                    passed, failed, errors = run_adoc_file(p_path, mode=mode)
            else:
                passed, failed, errors = run_path(p_path, mode=mode, fail_fast=fail_fast)

            total_passed += passed
            total_failed += failed
            all_errors.extend(errors)

            if verbose:
                if failed == 0:
                    if passed > 0:
                        click.echo(f"PASS: {p_path} ({passed} test(s))")
                    else:
                        click.echo(f"SKIP: {p_path} (0 tests)")
                else:
                    click.echo(f"FAIL: {p_path}")

            if fail_fast and failed > 0:
                break

    for err in all_errors:
        click.echo(err, err=True)

    if verbose or total_passed > 0 or total_failed > 0:
        click.echo(f"Doctest Summary: {total_passed} passed, {total_failed} failed")

    return 0 if total_failed == 0 else 1
