"""
= CLI Interface for Golem

This module provides the primary Click-based command-line interface for the
Golem static site generator.

== Subcommands

- `init`:: Initialize a new Golem project.
- `new`:: Create a new document skeleton.
- `build`:: Run the incremental compiler.
- `serve`:: Start the local development server.
- `plugins`:: Inspect installed and configured plugins.
- `themes`:: Inspect active and available themes.
"""

from pathlib import Path
from contextlib import contextmanager
import importlib.metadata
import json
import os
import shutil
from typing import Any, Iterator
import click
from golem.config import GolemConfig, load_config, find_default_config_path
from golem.engine import BuildEngine
from golem.plugins import get_plugin_manager

BUILTIN_PLUGINS: list[str] = ["golem.plugins.doctest", "golem.plugins.apidoc"]


@contextmanager
def change_working_dir(directory: Path | str | None) -> Iterator[None]:
    """Temporarily change the working directory within a context."""
    if not directory:
        yield
        return
    old_cwd = Path.cwd()
    new_dir = Path(directory).resolve()
    new_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(old_cwd)


def format_diagnostic(error: dict[str, Any] | Exception, content_dir: Path | str | None = None) -> str:
    """
    = format_diagnostic

    Format clean AsciiDoc compiler diagnostics with source coordinates and context snippets.

    === Examples

    [source,python]
    ----
    >>> err = {"file": "docs/02-architecture.adoc", "line": 14, "column": 5, "message": "Unclosed attribute list"}
    >>> "Error in docs/02-architecture.adoc:14:5" in format_diagnostic(err)
    True

    ----
    """
    if isinstance(error, Exception):
        exc: Any = error
        message = str(exc)
        file_path_raw = getattr(exc, "filename", getattr(exc, "file", None))
        line = getattr(exc, "lineno", getattr(exc, "line", None))
        column = getattr(exc, "offset", getattr(exc, "column", getattr(exc, "col_offset", None)))
    else:
        exc = error.get("exception")
        message = str(error.get("message", ""))
        file_path_raw = error.get("file") or (getattr(exc, "filename", getattr(exc, "file", None)) if exc else None)
        line = error.get("line") or (getattr(exc, "lineno", getattr(exc, "line", None)) if exc else None)
        column = (
            error.get("column")
            or error.get("col")
            or (
                getattr(
                    exc,
                    "offset",
                    getattr(exc, "column", getattr(exc, "col_offset", None)),
                )
                if exc
                else None
            )
        )

    # If line / column not found, parse coordinates from message if present
    if (line is None or column is None) and message:
        import re

        m_coord = re.search(r"(?:line\s*|:)(\d+)(?:,\s*col(?:umn)?\s*|:)(\d+)", message, re.IGNORECASE)
        if m_coord:
            if line is None:
                line = int(m_coord.group(1))
            if column is None:
                column = int(m_coord.group(2))
        else:
            m_line = re.search(r"(?:line\s*|:)(\d+)", message, re.IGNORECASE)
            if m_line and line is None:
                line = int(m_line.group(1))

    file_display = str(file_path_raw) if file_path_raw else "unknown"
    if file_path_raw:
        try:
            p = Path(file_path_raw)
            if p.is_absolute():
                try:
                    file_display = str(p.relative_to(Path.cwd()))
                except ValueError:
                    file_display = str(p)
            else:
                file_display = str(p)
        except Exception:
            file_display = str(file_path_raw)

    if line is not None and line > 0:
        if column is not None and column > 0:
            header = f"Error in {file_display}:{line}:{column}"
        else:
            header = f"Error in {file_display}:{line}"
    else:
        header = f"Error in {file_display}: {message}"

    lines: list[str] = []
    if file_path_raw:
        target_path = Path(file_path_raw)
        if not target_path.exists() and content_dir:
            alt_path = Path(content_dir) / target_path
            if alt_path.exists():
                target_path = alt_path

        if target_path.exists() and target_path.is_file():
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
            except Exception:
                lines = []

    if lines and line is not None and 1 <= line <= len(lines):
        start_line = max(1, line - 2)
        end_line = line
        margin_width = len(str(end_line))

        out_lines = [header]
        for ln in range(start_line, end_line + 1):
            line_text = lines[ln - 1]
            ln_str = str(ln).rjust(margin_width)
            if line_text:
                out_lines.append(f"{ln_str} | {line_text}")
            else:
                out_lines.append(f"{ln_str} |")

        col = column if (column is not None and column > 0) else 1
        col_idx = max(0, col - 1)
        pointer_margin = " " * margin_width
        out_lines.append(f"{pointer_margin} | {' ' * col_idx}^-- {message}")
        return "\n".join(out_lines)

    if line is not None and line > 0:
        return f"{header}\n  ^-- {message}"
    return header


class GolemGroup(click.Group):
    """Click Group that dynamically loads plugins for subcommands."""

    def _load_plugin_subcommands(self) -> None:
        config_path = find_default_config_path()
        try:
            config = load_config(config_path) if config_path.exists() else GolemConfig()
        except Exception:
            config = GolemConfig()
        pm = get_plugin_manager(config)
        pm.hook.golem_add_subcommands(cli=self)

    def list_commands(self, ctx: click.Context) -> list[str]:
        self._load_plugin_subcommands()
        return super().list_commands(ctx)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd
        self._load_plugin_subcommands()
        return super().get_command(ctx, cmd_name)


@click.group(cls=GolemGroup, invoke_without_command=True)
@click.option("--version", is_flag=True, help="Print version details")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
def main(version: bool = False, directory: str | None = None) -> None:
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
    with change_working_dir(directory):
        config_path = find_default_config_path()
        try:
            config = load_config(config_path) if config_path.exists() else GolemConfig()
        except Exception:
            config = GolemConfig()
        pm = get_plugin_manager(config)
        pm.hook.golem_add_subcommands(cli=main)

        if version:
            click.echo("Golem static site generator v0.1.0")


@main.command()
@click.option("--template", default="package", help="Project template type")
@click.option("--output-dir", help="Override build output directory")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
def init(template, output_dir, directory=None):
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

    | `-C`, `--directory`
    | Working directory path.
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
    ...     "Initializing golem project" in result.output
    True

    ----
    """
    with change_working_dir(directory):
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

            # Build output directory override if provided
            if output_dir:
                pass

        scaffold_docs = True
        if any(f.name not in ("static", "templates", ".DS_Store") for f in content_dir.iterdir()):
            try:
                scaffold_docs = click.confirm(
                    f"The directory '{content_dir}' is not empty. Scaffold default documentation files?",
                    default=False,
                )
            except click.Abort, Exception:
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
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
def new(doc_type, name, directory=None):
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
    >>> "Created new post" in result.output
    True

    ----
    """
    with change_working_dir(directory):
        config_path = find_default_config_path()
        try:
            config = load_config(config_path)
        except Exception as e:
            raise click.ClickException(f"Configuration Error: {e}")

        import re
        from datetime import datetime

        # Convert to lowercase kebab-case slug for the filename
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).lower().strip("-")
        if not slug:
            raise click.ClickException(f"Invalid document name: '{name}' resulting in an empty slug.")

        content_dir = Path(config.content_dir)
        target_file = content_dir / f"{slug}.adoc"

        if target_file.exists():
            raise click.ClickException(f"File already exists: {target_file}")

        target_file.parent.mkdir(parents=True, exist_ok=True)

        current_date = datetime.now().strftime("%Y-%m-%d")
        author = config.site_author

        template = f"""= {name}
:golem-type: {doc_type}
:author: {author}
:date: {current_date}

== Introduction

Welcome to your newly scaffolded {doc_type}: "{name}".
"""
        try:
            target_file.write_text(template, encoding="utf-8")
        except Exception as e:
            raise click.ClickException(f"Failed to create file {target_file}: {e}")

        click.echo(f"Created new {doc_type}: '{target_file}'")


@main.command()
@click.option(
    "--config",
    default="golem.toml",
    help="Path to primary configuration file",
)
@click.option("--clean", is_flag=True, help="Empty output directory before building")
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Fail compilation on syntax errors or parse warnings",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose diagnostic output",
)
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
def build(config, clean, strict, verbose, directory=None):
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
    with change_working_dir(directory):
        if verbose:
            import logging

            logging.basicConfig(level=logging.DEBUG, force=True)

        click.echo("Building static site...")

        config_path = Path(config)
        if config == "golem.toml" and not config_path.exists():
            config_path = find_default_config_path()

        try:
            golem_config = load_config(config_path)
        except Exception as e:
            raise click.ClickException(f"Configuration Error: {e}")

        if strict:
            golem_config.strict = True

        if clean:
            out_dir = Path(golem_config.output_dir)
            if out_dir.exists():
                shutil.rmtree(out_dir)
            # Invalidate local cache database on clean builds
            cache_file = Path(golem_config.content_dir).parent / ".golem" / "cache.json"
            if cache_file.exists():
                cache_file.unlink()

        try:
            engine = BuildEngine(golem_config)
            compiled = engine.build_site()
        except Exception as e:
            if hasattr(engine, "errors") and engine.errors:
                for err in engine.errors:
                    click.echo(format_diagnostic(err), err=True)
            raise click.ClickException(f"Compilation Error: {e}")

        if engine.errors:
            for err in engine.errors:
                click.echo(format_diagnostic(err))

        click.echo(f"Compilation finished. Built {len(compiled)} pages.")


@main.command()
@click.option("--port", default=8000, help="Local host port")
@click.option("--host", default="127.0.0.1", help="Local binding host")
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Fail compilation on syntax errors or parse warnings",
)
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
@click.option("--test-only", is_flag=True, hidden=True, help="Exit immediately for testing")
def serve(port, host, strict, directory=None, test_only=False):
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
    with change_working_dir(directory):
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
            try:
                golem_config = load_config(config_path)
            except Exception as e:
                raise click.ClickException(f"Configuration Error: {e}")

        if strict:
            golem_config.strict = True

        # Compile the site first
        click.echo("Building static site before serving...")
        try:
            engine = BuildEngine(golem_config)
            engine.build_site()
        except Exception as e:
            if hasattr(engine, "errors") and engine.errors:
                for err in engine.errors:
                    click.echo(format_diagnostic(err), err=True)
            raise click.ClickException(f"Compilation Error: {e}")

        if engine.errors:
            for err in engine.errors:
                click.echo(format_diagnostic(err))

        server = LiveReloadServer(
            public_dir=Path(golem_config.output_dir),
            watch_dir=Path(golem_config.content_dir),
            change_detected_func=lambda: bool(engine.get_outdated_files(commit=False)),
            rebuild_func=lambda: engine.build_site(),
            port=port,
            errors_func=lambda: engine.errors,
        )
        server.run()


@main.command()
@click.option("--json", "json_format", is_flag=True, help="Output structured JSON")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
def plugins(json_format: bool = False, directory: str | None = None) -> None:
    """
    = plugins

    Inspect active, installed, and local Golem plugins.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> result = runner.invoke(main, ["plugins"])
    >>> result.exit_code == 0
    True
    >>> "[ENABLED]" in result.output
    True

    ----
    """
    with change_working_dir(directory):
        config_path = find_default_config_path()
        try:
            config = load_config(config_path) if config_path.exists() else GolemConfig()
        except Exception:
            config = GolemConfig()

        builtin_plugin_names = BUILTIN_PLUGINS
        configured_plugins = list(config.plugins) if config.plugins else []

        plugins_list: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        # 1. Built-in plugins
        for name in builtin_plugin_names:
            is_enabled = name in configured_plugins
            plugins_list.append(
                {
                    "name": name,
                    "enabled": is_enabled,
                    "source": "built-in",
                    "description": "(built-in)",
                }
            )
            seen_names.add(name)

        # 2. Entry points
        eps: tuple[Any, ...] | list[Any]
        try:
            eps = list(importlib.metadata.entry_points(group="golem.plugins"))
        except Exception:
            eps = []

        for ep in eps:
            ep_name = getattr(ep, "name", str(ep))
            if ep_name in seen_names:
                continue
            dist = getattr(ep, "dist", None)
            if dist:
                dist_name = getattr(dist, "name", ep_name)
                dist_version = getattr(dist, "version", "")
                dist_desc = f"{dist_name} {dist_version}".strip() if dist_version else f"{dist_name}"
            else:
                dist_desc = ep_name
            ep_value = getattr(ep, "value", "")
            is_enabled = ep_name in configured_plugins or (bool(ep_value) and ep_value in configured_plugins)
            plugins_list.append(
                {
                    "name": ep_name,
                    "enabled": is_enabled,
                    "source": "entry_point",
                    "description": f"(entry_point: {dist_desc})",
                }
            )
            seen_names.add(ep_name)

        # 3. Local plugins in plugins_dir
        plugins_dir_path = Path(config.plugins_dir) if getattr(config, "plugins_dir", None) else Path("plugins")
        if plugins_dir_path.exists() and plugins_dir_path.is_dir():
            for py_file in sorted(plugins_dir_path.glob("*.py")):
                if py_file.name == "__init__.py":
                    continue
                stem = py_file.stem
                rel_path = f"{plugins_dir_path.as_posix()}/{py_file.name}"
                if stem in seen_names:
                    continue
                is_enabled = (
                    stem in configured_plugins
                    or py_file.name in configured_plugins
                    or f"{plugins_dir_path.name}.{stem}" in configured_plugins
                    or rel_path in configured_plugins
                )
                plugins_list.append(
                    {
                        "name": stem,
                        "enabled": is_enabled,
                        "source": "local",
                        "description": f"(local: {rel_path})",
                    }
                )
                seen_names.add(stem)

        # 4. Any other custom configured plugins
        for cfg_plugin in configured_plugins:
            if cfg_plugin not in seen_names:
                plugins_list.append(
                    {
                        "name": cfg_plugin,
                        "enabled": True,
                        "source": "custom",
                        "description": f"(custom: {cfg_plugin})",
                    }
                )
                seen_names.add(cfg_plugin)

        if json_format:
            click.echo(json.dumps(plugins_list, indent=2))
        else:
            for p in plugins_list:
                status_str = "[ENABLED]" if p["enabled"] else "[DISABLED]"
                click.echo(f"{status_str:<10} {p['name']} {p['description']}")


@main.command()
@click.option("--json", "json_format", is_flag=True, help="Output structured JSON")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
def themes(json_format: bool = False, directory: str | None = None) -> None:
    """
    = themes

    Inspect active and available Golem themes.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> result = runner.invoke(main, ["themes"])
    >>> result.exit_code == 0
    True
    >>> "Active Theme:" in result.output
    True

    ----
    """
    with change_working_dir(directory):
        config_path = find_default_config_path()
        try:
            config = load_config(config_path) if config_path.exists() else GolemConfig()
        except Exception:
            config = GolemConfig()

        active_theme = getattr(config, "theme", "default") or "default"
        themes_list: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        # 1. Built-in default theme
        themes_list.append(
            {
                "name": "default",
                "source": "built-in",
                "description": "(built-in)",
                "active": active_theme == "default",
            }
        )
        seen_names.add("default")

        # 2. Local themes directory
        themes_dir = Path("themes")
        if themes_dir.exists() and themes_dir.is_dir():
            for sub_dir in sorted(themes_dir.iterdir()):
                if sub_dir.is_dir() and not sub_dir.name.startswith("."):
                    name = sub_dir.name
                    if name not in seen_names:
                        themes_list.append(
                            {
                                "name": name,
                                "source": "local",
                                "description": f"(local: themes/{name})",
                                "active": active_theme == name,
                            }
                        )
                        seen_names.add(name)

        # 3. Entry points for golem.themes
        eps: tuple[Any, ...] | list[Any]
        try:
            eps = list(importlib.metadata.entry_points(group="golem.themes"))
        except Exception:
            eps = []

        for ep in eps:
            ep_name = getattr(ep, "name", str(ep))
            if ep_name not in seen_names:
                dist = getattr(ep, "dist", None)
                if dist:
                    dist_name = getattr(dist, "name", ep_name)
                    dist_version = getattr(dist, "version", "")
                    dist_desc = f"{dist_name} {dist_version}".strip() if dist_version else f"{dist_name}"
                else:
                    dist_desc = ep_name
                themes_list.append(
                    {
                        "name": ep_name,
                        "source": "entry_point",
                        "description": f"(entry_point: {dist_desc})",
                        "active": active_theme == ep_name,
                    }
                )
                seen_names.add(ep_name)

        # Determine active theme description
        active_entry = next((t for t in themes_list if t["name"] == active_theme), None)
        if active_entry:
            active_source = active_entry["description"]
        else:
            active_source = f"(custom: {active_theme})"
            themes_list.append(
                {
                    "name": active_theme,
                    "source": "custom",
                    "description": active_source,
                    "active": True,
                }
            )

        if json_format:
            theme_data = {
                "active": active_theme,
                "active_source": active_source,
                "themes": themes_list,
            }
            click.echo(json.dumps(theme_data, indent=2))
        else:
            click.echo(f"Active Theme: '{active_theme}' {active_source}\n")
            click.echo("Available Themes:")
            for t in themes_list:
                click.echo(f"  * {t['name']} {t['description']}")


if __name__ == "__main__":
    main()
