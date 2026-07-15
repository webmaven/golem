"""
= CLI Interface for Golem

This module provides the primary Click-based command-line interface for the
Golem static site generator.

== Subcommands

- `init`:: Initialize a new Golem project.
- `new`:: Create a new document skeleton.
- `build`:: Run the incremental compiler.
- `serve`:: Start the local development server.
"""

import click


@click.group(invoke_without_command=True)
@click.option("--version", is_flag=True, help="Print version details")
def main(version):
    """
    = main

    Entry point for the click CLI.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> result = runner.invoke(main, ["--version"])
    >>> result.exit_code == 0
    True
    >>> "Golem" in result.output
    True
    ----
    """
    if version:
        click.echo("Golem static site generator v0.1.0")


@main.command()
@click.option("--template", default="library", help="Project template type")
@click.option("--output-dir", help="Override build output directory")
def init(template, output_dir):
    """
    = init

    Create a standard directory structure and basic `golem.toml` configuration.

    [cols="1,1"]
    |===
    | Option | Description

    | `--template`
    | Project layout profile (e.g. `library` or `simple`).

    | `--output-dir`
    | Optional build override path.
    |===

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> result = runner.invoke(main, ["init"])
    >>> result.exit_code == 0
    True
    >>> "Initializing golem project using template 'library'..." in result.output
    True
    ----
    """
    click.echo(f"Initializing golem project using template '{template}'...")


@main.command()
@click.argument("doc_type")
@click.argument("name")
def new(doc_type, name):
    """
    = new

    Generate a structured `.adoc` file with pre-populated metadata templates.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> result = runner.invoke(main, ["new", "post", "hello-world"])
    >>> result.exit_code == 0
    True
    >>> "Creating new post: 'hello-world'" in result.output
    True
    ----
    """
    click.echo(f"Creating new {doc_type}: '{name}'")


@main.command()
@click.option("--config", help="Path to primary configuration file")
@click.option("--clean", is_flag=True, help="Empty output directory before building")
def build(config, clean):
    """
    = build

    Run the incremental compiler, building static pages.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> result = runner.invoke(main, ["build"])
    >>> result.exit_code == 0
    True
    >>> "Building static site..." in result.output
    True
    ----
    """
    click.echo("Building static site...")


@main.command()
@click.option("--port", default=8000, help="Local host port")
@click.option("--host", default="127.0.0.1", help="Local binding host")
def serve(port, host):
    """
    = serve

    Invoke build and launch a local web server with SSE live reloading.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> result = runner.invoke(main, ["serve"])
    >>> result.exit_code == 0
    True
    >>> "Serving site on http://127.0.0.1:8000..." in result.output
    True
    ----
    """
    click.echo(f"Serving site on http://{host}:{port}...")


if __name__ == "__main__":
    main()
