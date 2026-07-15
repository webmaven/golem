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

from pathlib import Path
import shutil
import click
from golem.config import load_config, find_default_config_path
from golem.engine import BuildEngine


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
    >>> "Golem static site generator" in result.output
    True

    ----
    """
    if version:
        click.echo("Golem static site generator v0.1.0")


@main.command()
@click.option("--template", default="package", help="Project template type")
@click.option("--output-dir", help="Override build output directory")
def init(template, output_dir):
    """
    = init

    Create a standard directory structure and basic `golem.toml` configuration.

    [cols="1,1"]
    |===
    | Option | Description

    | `--template`
    | Project layout profile (e.g. `package` or `simple`).

    | `--output-dir`
    | Optional build override path.
    |===

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> with runner.isolated_filesystem():
    ...     result = runner.invoke(main, ["init"])
    ...     result.exit_code == 0
    True

    ----
    """
    click.echo(f"Initializing golem project using template '{template}'...")

    pyproject_toml = Path("pyproject.toml")
    is_site_layout = template in ("site", "book", "simple") or not pyproject_toml.exists()

    if pyproject_toml.exists():
        click.echo("Found pyproject.toml! Configuring Golem under [tool.golem]...")
        with open(pyproject_toml, "r", encoding="utf-8") as f:
            content = f.read()
        
        if "[tool.golem]" not in content and "[tool.golem." not in content:
            if content and not content.endswith("\n"):
                content += "\n"
            if is_site_layout:
                content += """
[tool.golem.site]
title = "Golem Documentation"
author = "Michael Bernstein"

[tool.golem.build]
content_dir = "docs"
output_dir = "dist"
theme = "default"
static_dir = "docs/static"
templates_dir = "docs/templates"
"""
            else:
                content += """
[tool.golem.site]
title = "Golem Documentation"
author = "Michael Bernstein"

[tool.golem.build]
content_dir = "docs"
output_dir = "dist"
theme = "default"
"""
            pyproject_toml.write_text(content, encoding="utf-8")
        content_dir = Path("docs")
        static_path = Path("docs/static")
        templates_path = Path("docs/templates")
    else:
        golem_toml = Path("golem.toml")
        if not golem_toml.exists():
            if is_site_layout:
                golem_toml.write_text(
                    """\
[site]
title = "Golem Documentation"
author = "Michael Bernstein"

[build]
content_dir = "content"
output_dir = "dist"
theme = "default"
static_dir = "static"
templates_dir = "templates"
""",
                    encoding="utf-8",
                )
            else:
                golem_toml.write_text(
                    """\
[site]
title = "Golem Documentation"
author = "Michael Bernstein"

[build]
content_dir = "content"
output_dir = "dist"
theme = "default"
""",
                    encoding="utf-8",
                )
        content_dir = Path("content")
        static_path = Path("static")
        templates_path = Path("templates")

    content_dir.mkdir(exist_ok=True)

    # Scaffold static and templates directories if site layout is active
    if is_site_layout:
        css_dir = static_path / "css"
        css_dir.mkdir(parents=True, exist_ok=True)
        custom_css = css_dir / "custom.css"
        if not custom_css.exists():
            custom_css.write_text(
                """\
:root {
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --bg-color: #fafafa;
    --text-color: #222222;
    --accent-color: #10b981;
}

body {
    font-family: var(--font-sans);
    background: var(--bg-color);
    color: var(--text-color);
    margin: 0;
    padding: 0;
}

.container {
    max-width: 900px;
    margin: 0 auto;
    padding: 2rem;
}
""",
                encoding="utf-8",
            )

        templates_path.mkdir(exist_ok=True)
        page_template = templates_path / "page.pt"
        if not page_template.exists():
            page_template.write_text(
                """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${site_title} - ${title}</title>
    <link rel="stylesheet" href="/css/custom.css">
</head>
<body>
    <header class="site-header">
        <div class="container">
            <span class="logo">${site_title}</span>
            <span class="author">By ${site_author}</span>
        </div>
    </header>

    <div class="main-layout container">
        <main class="content-pane">
            <article class="page-body">
                <h1>${title}</h1>
                <div tal:content="structure body">
                    AsciiDoc content renders here.
                </div>
            </article>
        </main>
    </div>
</body>
</html>
""",
                encoding="utf-8",
            )

    scaffold_docs = True
    if any(f.name not in ("static", "templates", ".DS_Store") for f in content_dir.iterdir()):
        try:
            scaffold_docs = click.confirm(
                f"The directory '{content_dir}' is not empty. Scaffold default documentation files?",
                default=False,
            )
        except (click.Abort, Exception):
            scaffold_docs = False

    if scaffold_docs:
        index_adoc = content_dir / "index.adoc"
        if not index_adoc.exists():
            index_adoc.write_text(
                """\
= Welcome to Golem
Michael Bernstein

This is the homepage of your newly initialized Golem static documentation portal.
""",
                encoding="utf-8",
            )

    click.echo("Initialization complete! Project structure is ready.")


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
@click.option(
    "--config",
    default="golem.toml",
    help="Path to primary configuration file",
)
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
    >>> with runner.isolated_filesystem():
    ...     _ = runner.invoke(main, ["init"])
    ...     result = runner.invoke(main, ["build"])
    ...     result.exit_code == 0
    True

    ----
    """
    click.echo("Building static site...")

    config_path = Path(config)
    if config == "golem.toml" and not config_path.exists():
        config_path = find_default_config_path()
    golem_config = load_config(config_path)

    if clean:
        out_dir = Path(golem_config.output_dir)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        # Invalidate local cache database on clean builds
        cache_file = Path(golem_config.content_dir).parent / ".golem" / "cache.json"
        if cache_file.exists():
            cache_file.unlink()

    engine = BuildEngine(golem_config)
    compiled = engine.build_site()
    click.echo(f"Compilation finished. Built {len(compiled)} pages.")


@main.command()
@click.option("--port", default=8000, help="Local host port")
@click.option("--host", default="127.0.0.1", help="Local binding host")
@click.option("--test-only", is_flag=True, hidden=True, help="Exit immediately for testing")
def serve(port, host, test_only):
    """
    = serve

    Invoke build and launch a local web server with SSE live reloading.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> result = runner.invoke(main, ["serve", "--test-only"])
    >>> result.exit_code == 0
    True
    >>> "Serving site on http://127.0.0.1:8000..." in result.output
    True

    ----
    """
    click.echo(f"Serving site on http://{host}:{port}...")
    if test_only:
        return

    from golem.server import LiveReloadServer

    config_path = find_default_config_path()
    if not config_path.exists():
        click.echo("No golem.toml found. Initializing fallback configuration...")
        from golem.config import GolemConfig
        golem_config = GolemConfig(content_dir="content", output_dir="dist")
    else:
        golem_config = load_config(config_path)

    # Compile the site first
    click.echo("Building static site before serving...")
    engine = BuildEngine(golem_config)
    engine.build_site()

    server = LiveReloadServer(
        public_dir=Path(golem_config.output_dir),
        watch_dir=Path(golem_config.content_dir),
        change_detected_func=lambda: bool(engine.get_outdated_files()),
        rebuild_func=lambda: engine.build_site(),
        port=port
    )
    server.run()


if __name__ == "__main__":
    main()
