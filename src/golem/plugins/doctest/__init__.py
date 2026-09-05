from __future__ import annotations

from pathlib import Path
from typing import Sequence
import click

from golem.plugins import hookimpl
from .runner import (
    run_adoc_file,
    run_all,
    run_docstring_tests,
    run_path,
)

__all__ = [
    "golem_add_subcommands",
    "run_asciidoc_doctests",
    "run_doctests",
    "run_adoc_file",
    "run_docstring_tests",
    "run_path",
    "run_all",
]


def run_doctests(
    paths: Sequence[Path | str] | None = None,
    source: str | None = None,
    mode: str = "explicit",
    verbose: bool = False,
    fail_fast: bool = False,
    split_sections: bool = False,
) -> int:
    """Programmatic entry point to run AsciiDoc doctests."""
    target_paths: list[Path | str] = []
    if paths:
        target_paths.extend(paths)
    elif not source:
        # Fallback to config content_dir or docs directory
        from golem.config import find_default_config_path, load_config

        config_path = find_default_config_path()
        if config_path.exists():
            try:
                config = load_config(config_path)
                content_dir = Path(config.content_dir)
                if content_dir.exists():
                    target_paths.append(content_dir)
            except Exception:
                pass
        if not target_paths:
            docs_dir = Path("docs")
            if docs_dir.exists():
                target_paths.append(docs_dir)
            else:
                return 0

    return run_all(
        paths=target_paths,
        source=source,
        mode=mode,
        verbose=verbose,
        fail_fast=fail_fast,
        split_sections=split_sections,
    )


# Alias for backward compatibility / explicit naming
run_asciidoc_doctests = run_doctests


@hookimpl
def golem_add_subcommands(cli: click.Group) -> None:
    """Register the 'doctest' subcommand with Click CLI."""

    @cli.command("doctest")
    @click.argument("paths", nargs=-1, type=click.Path())
    @click.option(
        "-m",
        "--mode",
        type=click.Choice(["explicit", "eager", "auto"]),
        default="explicit",
        help="DocTest execution mode (explicit, eager, auto)",
    )
    @click.option(
        "-s",
        "--source",
        default=None,
        help="Python package or source file to extract docstring tests from",
    )
    @click.option(
        "-v",
        "--verbose",
        is_flag=True,
        default=False,
        help="Show detailed per-block test progress and outputs",
    )
    @click.option(
        "-x",
        "--fail-fast",
        is_flag=True,
        default=False,
        help="Stop immediately on the first test failure",
    )
    @click.option(
        "--split-sections",
        is_flag=True,
        default=False,
        help="Split doctest execution per section rather than per document",
    )
    def doctest_command(
        paths: tuple[str, ...],
        mode: str = "explicit",
        source: str | None = None,
        verbose: bool = False,
        fail_fast: bool = False,
        split_sections: bool = False,
    ) -> None:
        """Run interactive AsciiDoc doctests on documentation and source files."""
        exit_code = run_doctests(
            paths=list(paths) if paths else None,
            source=source,
            mode=mode,
            verbose=verbose,
            fail_fast=fail_fast,
            split_sections=split_sections,
        )
        if exit_code != 0:
            raise click.exceptions.Exit(exit_code)
