"""

This module provides the primary Click-based command-line interface for the
Golem static site generator.

== Subcommands

- `init`:: Initialize a new Golem project.
- `new`:: Create a new document skeleton.
- `build`:: Run the incremental compiler.
- `check`:: Check AsciiDoc source files for syntax errors and semantic resolver warnings.
- `serve`:: Start the local development server.
- `plugins`:: Inspect installed and configured plugins.
- `themes`:: Inspect active and available themes.
"""

from pathlib import Path
from contextlib import contextmanager
import datetime
import importlib.metadata
import json
import os
import shutil
import sys
import time
from typing import Any, Iterator
import click
from golem.config import GolemConfig, load_config, find_default_config_path
from golem.diagnostics import format_diagnostic
from golem.engine import BuildEngine, GolemEngine
from golem.plugins import get_plugin_manager

__all__ = ["check", "main", "report_engine_diagnostics", "PROFILE_NAMES"]

PROFILE_NAMES: frozenset[str] = frozenset({"library", "cli", "paper", "blog"})


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


def _resolve_effective_directory(ctx: click.Context | None, explicit_dir: Path | str | None) -> Path | str | None:
    """Resolve the working directory from an explicit argument or ancestor Click contexts."""
    if explicit_dir:
        return explicit_dir
    curr = ctx
    while curr is not None:
        if hasattr(curr, "params") and curr.params.get("directory"):
            return curr.params["directory"]
        curr = curr.parent
    return None


class NewGroup(GolemGroup):
    """Click Group for `golem new` that defaults to document scaffolding for unknown subcommands."""

    def __init__(self, *args: Any, default_cmd: click.Command | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.default_cmd = default_cmd

    def resolve_command(self, ctx: click.Context, args: list[str]) -> tuple[str | None, click.Command | None, list[str]]:
        cmd_name = args[0] if args else None
        cmd = self.get_command(ctx, cmd_name) if cmd_name else None
        if cmd is not None:
            return cmd_name, cmd, args[1:]
        if cmd_name and not cmd_name.startswith("-") and self.default_cmd is not None:
            return self.default_cmd.name or "document", self.default_cmd, args
        return super().resolve_command(ctx, args)


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
            try:
                _ver = importlib.metadata.version("golem-docs")
            except importlib.metadata.PackageNotFoundError:
                _ver = "dev"
            click.echo(f"Golem static site generator v{_ver}")


def _get_git_author() -> str:
    """Read the git global user.name; return a placeholder on failure."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "config", "--global", "user.name"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        name = result.stdout.strip()
        return name if name else "Your Name"
    except Exception:
        return "Your Name"


def _scaffold_profile(profile: str, target_dir: Path, variables: dict[str, str]) -> None:
    """Copy a profile's template files into target_dir with {{var}} substitution."""
    profiles_dir = Path(__file__).parent / "templates" / "profiles" / profile
    if not profiles_dir.exists():
        raise click.ClickException(f"Profile template not found: {profile!r}")

    def _render(text: str) -> str:
        for key, val in variables.items():
            text = text.replace("{{" + key + "}}", val)
        return text

    for src in sorted(profiles_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(profiles_dir)
        parts = list(rel.parts)
        # Substitute variables in all path parts (including filename)
        rendered_parts = [_render(p) for p in parts]
        # Strip .tmpl from the last path component
        if rendered_parts[-1].endswith(".tmpl"):
            rendered_parts[-1] = rendered_parts[-1][: -len(".tmpl")]
        dest = target_dir / Path(*rendered_parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_render(src.read_text(encoding="utf-8")), encoding="utf-8")


@main.command()
@click.option(
    "--profile",
    default="package",
    help="Project profile (library, cli, paper, blog, package, site, simple)",
)
@click.option("--output-dir", help="Override build output directory")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
def init(profile, output_dir, directory=None):
    """

    Create a standard directory structure and basic `golem.toml` configuration.

    [cols="1,1"]
    |===
    | Option | Description

    | `--profile`
    | Project profile (library, cli, paper, blog, package, site, simple).

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
        # Default author for legacy profiles (package, site, simple, book).
        # Profile-specific init overrides this via pyproject.toml extraction or click.prompt().
        author = _get_git_author()
        click.echo(f"Initializing golem project using profile '{profile}'...")

        if profile in PROFILE_NAMES:
            # Determine project_name and author from pyproject.toml or interactive prompts
            project_name = ""
            author_from_pp = ""
            _pyproject = Path("pyproject.toml")
            if _pyproject.exists():
                try:
                    if sys.version_info >= (3, 11):
                        import tomllib

                        with open(_pyproject, "rb") as _f:
                            _pp = tomllib.load(_f)
                    else:
                        import tomli as tomllib  # noqa: PLC0415

                        with open(_pyproject, "rb") as _f:
                            _pp = tomllib.load(_f)
                    _proj = _pp.get("project", {})
                    if isinstance(_proj, dict):
                        project_name = _proj.get("name", "")
                        _authors = _proj.get("authors", [])
                        if _authors and isinstance(_authors[0], dict):
                            author_from_pp = _authors[0].get("name", "")
                except Exception:
                    pass

            if not project_name:
                try:
                    project_name = click.prompt("Project name", default=Path.cwd().name)
                except (click.Abort, EOFError):
                    project_name = Path.cwd().name
            if not author_from_pp:
                try:
                    author = click.prompt("Author", default=_get_git_author())
                except (click.Abort, EOFError):
                    author = _get_git_author()
            else:
                author = author_from_pp

            year = str(datetime.date.today().year)
            variables = {"project_name": project_name, "author": author, "year": year}
            _scaffold_profile(profile, Path("."), variables)
            click.echo("Initialization complete! Project structure is ready.")
            return

        pyproject_toml = Path("pyproject.toml")
        is_site_layout = profile in ("site", "book", "simple") or not pyproject_toml.exists()

        if pyproject_toml.exists():
            click.echo("Found pyproject.toml! Configuring Golem under [tool.golem]...")
            with open(pyproject_toml, "r", encoding="utf-8") as f:
                content = f.read()

            if "[tool.golem]" not in content and "[tool.golem." not in content:
                if content and not content.endswith("\n"):
                    content += "\n"
                if is_site_layout:
                    content += f"""
[tool.golem.site]
title = "Golem Documentation"
author = "{author}"

[tool.golem.build]
content_dir = "docs"
output_dir = "dist"
theme = "default"
static_dir = "docs/static"
templates_dir = "docs/templates"
"""
                else:
                    content += f"""
[tool.golem.site]
title = "Golem Documentation"
author = "{author}"

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
                        f"""\
[site]
title = "Golem Documentation"
author = "{author}"

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
                        f"""\
[site]
title = "Golem Documentation"
author = "{author}"

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
                <div tal:content="structure body_html">
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
            except (click.Abort, Exception):
                scaffold_docs = False

        if scaffold_docs:
            index_adoc = content_dir / "index.adoc"
            if not index_adoc.exists():
                index_adoc.write_text(
                    f"""\
= Welcome to Golem
{author}

This is the homepage of your newly initialized Golem static documentation portal.
""",
                    encoding="utf-8",
                )

        click.echo("Initialization complete! Project structure is ready.")


@click.command(name="document", hidden=True)
@click.argument("doc_type")
@click.argument("name")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
@click.pass_context
def new_document(ctx: click.Context, doc_type: str, name: str, directory: str | None = None) -> None:
    """Generate a structured `.adoc` file with pre-populated metadata templates.

    [parameters]
    `ctx` (click.Context):: Click context object.
    `doc_type` (str):: Document category or classification (such as post, page, chapter).
    `name` (str):: Human-readable document title.
    `directory` (str | None, optional):: Project directory path. Defaults to `None`.

    [raises]
    `click.ClickException`:: If configuration fails, slug is invalid, or target file exists.
    """
    effective_dir = _resolve_effective_directory(ctx, directory)
    with change_working_dir(effective_dir):
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


@main.group(cls=NewGroup, default_cmd=new_document)
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
@click.pass_context
def new(ctx: click.Context, directory: str | None = None) -> None:
    """Generate structured AsciiDoc documents, custom themes, or plugins.

    Running `golem new <doc_type> <name>` scaffolds an AsciiDoc document
    with pre-populated metadata templates (for example, `golem new post hello-world`).

    Running `golem new theme <name>` scaffolds a complete custom theme.

    Running `golem new plugin <name>` scaffolds a local Python plugin.

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
    ctx.ensure_object(dict)
    if directory:
        ctx.obj["directory"] = directory


new.add_command(new_document, name="document")


@new.command(name="theme")
@click.argument("name")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
@click.pass_context
def new_theme(ctx: click.Context, name: str, directory: str | None = None) -> None:
    """Scaffold a new custom Golem theme with templates, styles, and configuration.

    [parameters]
    `ctx` (click.Context):: Click context object.
    `name` (str):: Theme name or slug.
    `directory` (str | None, optional):: Project directory path. Defaults to `None`.

    [raises]
    `click.ClickException`:: If the theme slug is empty or target directory already exists and is non-empty.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> with runner.isolated_filesystem():
    ...     res = runner.invoke(main, ["new", "theme", "clean-slate"])
    ...     res.exit_code == 0
    True
    ----
    """
    import re

    effective_dir = _resolve_effective_directory(ctx, directory)
    with change_working_dir(effective_dir):
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).lower().strip("-")
        if not slug:
            raise click.ClickException(f"Invalid theme name: '{name}' resulting in an empty slug.")

        target_dir = Path("themes") / slug
        if target_dir.exists() and any(target_dir.iterdir()):
            raise click.ClickException(f"Theme directory '{target_dir}' already exists and is not empty.")

        config_path = find_default_config_path()
        try:
            config = load_config(config_path) if config_path.exists() else GolemConfig()
        except Exception:
            config = GolemConfig()

        author = getattr(config, "site_author", None) or _get_git_author()

        target_dir.mkdir(parents=True, exist_ok=True)
        templates_dir = target_dir / "templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        css_dir = target_dir / "static" / "css"
        css_dir.mkdir(parents=True, exist_ok=True)

        skeleton_pt = f"""<!DOCTYPE html>
<html lang="en" metal:define-macro="layout">
<head metal:define-slot="head">
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${{title}} - ${{site_title}}</title>
    <meta name="generator" content="${{generator_version | nothing}}" />
    <meta tal:condition="site_author | nothing" name="author" content="${{site_author}}" />
    <link rel="canonical" tal:condition="site_url | nothing" href="${{site_url}}" />
    <link rel="stylesheet" href="${{root_path}}static/css/{slug}.css" />
    <tal:block tal:repeat="css_file custom_css | nothing">
        <link rel="stylesheet" href="${{css_file}}" />
    </tal:block>
    <style tal:condition="pygments_css | nothing" tal:content="structure pygments_css"></style>
</head>
<body tal:attributes="class body_class | nothing">
    <header class="site-header" metal:define-slot="header">
        <div class="container">
            <h1><a href="${{site_url or root_path}}">${{site_title}}</a></h1>
            <span tal:condition="site_author | nothing" class="site-author">${{site_author}}</span>
        </div>
    </header>
    <div class="site-container">
        <nav tal:condition="nav_html | nothing" class="site-nav" metal:define-slot="navigation" tal:content="structure nav_html"></nav>
        <main id="golem-content" class="site-main" metal:define-slot="content">
            <article class="content">
                <h1>${{title}}</h1>
                <div tal:content="structure body_html"></div>
            </article>
        </main>
        <aside tal:condition="toc_html | nothing" class="site-toc" metal:define-slot="table-of-contents" tal:content="structure toc_html"></aside>
    </div>
    <footer class="site-footer" metal:define-slot="footer">
        <div class="container">
            <p>Built with Golem v${{generator_version | nothing}}</p>
        </div>
    </footer>
</body>
</html>
"""

        layout_pt = f"""<metal:block define-macro="layout">
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${{title}} - ${{site_title}}</title>
    <link rel="stylesheet" href="${{root_path}}static/css/{slug}.css" />
</head>
<body tal:attributes="class body_class or None">
    <header class="site-header">
        <div class="container">
            <h1><a href="${{site_url or root_path}}">${{site_title}}</a></h1>
        </div>
    </header>
    <div class="site-container">
        <main id="golem-content" class="site-main" metal:define-slot="content">
            <article class="content">
                <h1>${{title}}</h1>
                <div tal:content="structure body_html"></div>
            </article>
        </main>
    </div>
</body>
</html>
</metal:block>
"""

        page_pt = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${{title}} - ${{site_title}}</title>
    <link rel="stylesheet" href="${{root_path}}static/css/{slug}.css" />
</head>
<body tal:attributes="class body_class or None">
    <header class="site-header">
        <div class="container">
            <h1><a href="${{site_url or root_path}}">${{site_title}}</a></h1>
            <span tal:condition="site_author" class="site-author">${{site_author}}</span>
        </div>
    </header>
    <div class="site-container">
        <main id="golem-content" class="site-main">
            <article class="content">
                <h1>${{title}}</h1>
                <div tal:content="structure body_html"></div>
            </article>
        </main>
    </div>
</body>
</html>
"""

        css_content = f"""\
/* {slug} theme stylesheet */
:root {{
    --color-bg: #ffffff;
    --color-text: #1a1a1a;
    --color-primary: #2563eb;
    --color-border: #e5e7eb;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}}

[data-theme="dark"] {{
    --color-bg: #111827;
    --color-text: #f9fafb;
    --color-primary: #3b82f6;
    --color-border: #374151;
}}

body {{
    margin: 0;
    font-family: var(--font-sans);
    background-color: var(--color-bg);
    color: var(--color-text);
    line-height: 1.6;
}}

.site-container {{
    display: flex;
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem 2rem;
    gap: 2rem;
}}

.site-header {{
    border-bottom: 1px solid var(--color-border);
    padding: 1rem 2rem;
}}

.site-main {{
    flex: 1;
    min-width: 0;
}}

.site-nav {{
    width: 240px;
}}

.site-toc {{
    width: 200px;
}}
"""

        theme_toml = f"""[theme]
name = "{slug}"
version = "0.1.0"
description = "Custom theme {slug} for Golem documentation portals"
author = "{author}"
"""

        readme_md = f"""# {slug} Theme

Custom theme for Golem documentation portals.

## Activating the Theme

Configure your project to use this theme:

In `golem.toml`:

```toml
[build]
theme = "{slug}"
```

Or in `pyproject.toml`:

```toml
[tool.golem.build]
theme = "{slug}"
```

## Structure

- `skeleton.pt`: Foundational HTML layout template with METAL slots.
- `page.pt`: Standard documentation page template.
- `layout.pt`: Main layout macro definition.
- `templates/`: Secondary template search path matching workspace standards.
- `static/css/{slug}.css`: Main theme styling and CSS custom properties.
- `static/css/theme.css`: Standard theme stylesheet alias.
- `theme.toml`: Theme metadata.
"""

        # Write core templates
        (target_dir / "skeleton.pt").write_text(skeleton_pt, encoding="utf-8")
        (target_dir / "layout.pt").write_text(layout_pt, encoding="utf-8")
        (target_dir / "page.pt").write_text(page_pt, encoding="utf-8")

        # Write template directory files
        (templates_dir / "skeleton.pt").write_text(skeleton_pt, encoding="utf-8")
        (templates_dir / "layout.pt").write_text(layout_pt, encoding="utf-8")
        (templates_dir / "page.pt").write_text(page_pt, encoding="utf-8")

        # Write CSS
        (css_dir / f"{slug}.css").write_text(css_content, encoding="utf-8")
        (css_dir / "theme.css").write_text(css_content, encoding="utf-8")

        # Write metadata
        (target_dir / "theme.toml").write_text(theme_toml, encoding="utf-8")
        (target_dir / "README.md").write_text(readme_md, encoding="utf-8")

        click.echo(f"""Created new theme '{slug}' in '{target_dir}':
  - {target_dir}/skeleton.pt
  - {target_dir}/page.pt
  - {target_dir}/layout.pt
  - {target_dir}/templates/skeleton.pt
  - {target_dir}/templates/page.pt
  - {target_dir}/templates/layout.pt
  - {target_dir}/static/css/{slug}.css
  - {target_dir}/static/css/theme.css
  - {target_dir}/theme.toml
  - {target_dir}/README.md

To activate this theme:
  In golem.toml:
    [build]
    theme = "{slug}"

  Or in pyproject.toml:
    [tool.golem.build]
    theme = "{slug}"\
""")


@new.command(name="plugin")
@click.argument("name")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
@click.pass_context
def new_plugin(ctx: click.Context, name: str, directory: str | None = None) -> None:
    """Scaffold a new custom Golem plugin with standard lifecycle hooks.

    [parameters]
    `ctx` (click.Context):: Click context object.
    `name` (str):: Plugin module name or identifier.
    `directory` (str | None, optional):: Project directory path. Defaults to `None`.

    [raises]
    `click.ClickException`:: If the plugin name cannot form a valid identifier or file exists.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> with runner.isolated_filesystem():
    ...     res = runner.invoke(main, ["new", "plugin", "my-plugin"])
    ...     res.exit_code == 0
    True
    ----
    """
    import re

    effective_dir = _resolve_effective_directory(ctx, directory)
    with change_working_dir(effective_dir):
        mod_name = re.sub(r"[^a-zA-Z0-9_]+", "_", name).lower().strip("_")
        if mod_name and mod_name[0].isdigit():
            mod_name = f"plugin_{mod_name}"
        if not mod_name or not mod_name.isidentifier():
            raise click.ClickException(f"Invalid plugin name: '{name}'. Must result in a valid Python identifier.")

        config_path = find_default_config_path()
        try:
            config = load_config(config_path) if config_path.exists() else GolemConfig()
        except Exception:
            config = GolemConfig()

        plugins_dir = Path(getattr(config, "plugins_dir", "plugins") or "plugins")
        target_file = plugins_dir / f"{mod_name}.py"

        if target_file.exists():
            raise click.ClickException(f"Plugin file already exists: {target_file}")

        target_file.parent.mkdir(parents=True, exist_ok=True)

        plugin_title = " ".join(part.capitalize() for part in mod_name.split("_"))

        template = f'''\
"""
= {plugin_title} Plugin for Golem

Custom plugin providing build lifecycle hooks and template context extensions.

[attributes]
`name` (str):: Plugin registration identifier.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from golem.plugins import hookimpl

if TYPE_CHECKING:
    from golem.config import GolemConfig
    from golem.model import PageContext

logger = logging.getLogger("{mod_name}")


@hookimpl
def on_build_start(config: GolemConfig) -> None:
    """Execute pre-flight checks before compilation begins.

    [parameters]
    `config` (GolemConfig):: Active site configuration for this build.
    """
    logger.info("Initializing {plugin_title} plugin for build...")


@hookimpl
def on_template_context(context: PageContext, doc_path: Path) -> PageContext:
    """Enrich the template context before Chameleon HTML rendering.

    [parameters]
    `context` (PageContext):: Active template context dictionary.
    `doc_path` (Path):: Path to the source document being compiled.

    [returns]
    `PageContext`:: Enriched template context.
    """
    context["{mod_name}_active"] = True
    return context


@hookimpl
def on_post_render(html_content: str) -> str:
    """Transform compiled HTML content prior to writing to disk.

    [parameters]
    `html_content` (str):: Rendered HTML document markup.

    [returns]
    `str`:: Transformed HTML markup.
    """
    return html_content
'''
        try:
            target_file.write_text(template, encoding="utf-8")
        except Exception as e:
            raise click.ClickException(f"Failed to create plugin file {target_file}: {e}")

        click.echo(f"""Created new plugin '{mod_name}' at '{target_file}'.

To enable this plugin:
  In golem.toml:
    [build]
    plugins = ["{mod_name}"]

  Or in pyproject.toml:
    [tool.golem.build]
    plugins = ["{mod_name}"]\
""")


def report_engine_diagnostics(engine: BuildEngine, strict: bool = False) -> None:
    """Print compiler diagnostics for the build engine and fail if strict mode is enabled.

    === Examples

    [source,python]
    ----
    >>> from golem.config import GolemConfig
    >>> from golem.engine import BuildEngine
    >>> from golem.cli import report_engine_diagnostics
    >>> engine = BuildEngine(GolemConfig())
    >>> report_engine_diagnostics(engine, strict=False)

    ----

    [parameters]
    `engine` (BuildEngine):: The build engine containing accumulated diagnostics.
    `strict` (bool, optional):: Whether to raise an exception on error diagnostics. Defaults to `False`.

    [raises]
    `click.ClickException`:: If `strict` is `True` and one or more diagnostics have error severity.
    """
    if not hasattr(engine, "diagnostics") or not engine.diagnostics:
        return
    for diag in engine.diagnostics:
        click.echo(format_diagnostic(diag), err=True)
    if strict and any(d.severity == "error" for d in engine.diagnostics):
        raise click.ClickException("Compilation failed due to build diagnostics in strict mode.")


@main.command()
@click.option(
    "--config",
    default="golem.toml",
    help="Path to primary configuration file",
)
@click.option("--clean", is_flag=True, help="Empty output directory before building")
@click.option(
    "--partial",
    "partial_targets",
    type=click.Path(),
    multiple=True,
    default=(),
    help="Rebuild only specified file or directory paths without wiping other outputs (can specify multiple)",
)
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
    "-q",
    "--quiet",
    is_flag=True,
    default=False,
    help="Silence non-error build output",
)
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
def build(config, clean, partial_targets, strict, verbose, quiet, directory=None):
    """

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
        if clean and partial_targets:
            raise click.ClickException("Options --clean and --partial are mutually exclusive.")

        import time

        start_time = time.perf_counter()

        if verbose:
            import logging

            logging.basicConfig(level=logging.DEBUG, force=True)

        if not quiet:
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
        if quiet:
            golem_config.quiet = True

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
            compiled = engine.build_site(partial_targets=partial_targets)
        except click.ClickException:
            raise
        except Exception as e:
            report_engine_diagnostics(engine, strict=strict)
            raise click.ClickException(f"Compilation Error: {e}")

        report_engine_diagnostics(engine, strict=strict)

        elapsed = time.perf_counter() - start_time
        if not quiet:
            click.echo(f"Compilation finished. Built {len(compiled)} pages in {elapsed:.2f}s.")


@main.command("check")
@click.option("--strict", is_flag=True, default=False, help="Fail if any syntax errors or diagnostics are found")
@click.option(
    "-C",
    "--directory",
    type=click.Path(file_okay=False, dir_okay=True),
    help="Change working directory before executing",
)
@click.option("-v", "--verbose", is_flag=True, default=False, help="Display verbose diagnostic outputs")
def check(strict: bool, directory: str | None = None, verbose: bool = False) -> None:
    """Check AsciiDoc source files for syntax errors and semantic resolver warnings without building.

    === Examples

    [source,python]
    ----
    >>> from click.testing import CliRunner
    >>> from golem.cli import main
    >>> runner = CliRunner()
    >>> with runner.isolated_filesystem():
    ...     result = runner.invoke(main, ["check"])
    ...     result.exit_code == 0
    True

    ----

    [parameters]
    `strict` (bool):: Fail if any syntax errors or diagnostics are found. Defaults to `False`.
    `directory` (str | None, optional):: Change working directory before executing. Defaults to `None`.
    `verbose` (bool):: Display verbose diagnostic outputs. Defaults to `False`.

    [raises]
    `click.ClickException`:: If syntax errors are found, or if diagnostics/warnings are found in strict mode.
    """
    with change_working_dir(directory):
        if verbose:
            import logging

            logging.basicConfig(level=logging.DEBUG, force=True)

        config_path = find_default_config_path()
        try:
            golem_config = load_config(config_path) if config_path.exists() else GolemConfig()
        except Exception as e:
            raise click.ClickException(f"Configuration Error: {e}")

        if strict:
            golem_config.strict = True

        if not config_path.exists() and not Path(golem_config.content_dir).exists() and Path("docs").is_dir():
            golem_config.content_dir = "docs"

        engine = GolemEngine(golem_config)
        engine.check()

        report_engine_diagnostics(engine, strict=strict)

        has_errors = any(d.severity == "error" for d in engine.diagnostics)
        has_warnings = any(d.severity == "warning" for d in engine.diagnostics)

        if has_errors:
            raise click.ClickException("Syntax errors encountered during check.")
        if strict and has_warnings:
            raise click.ClickException("Diagnostic warnings encountered during check in strict mode.")


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
        start_time = time.perf_counter()
        try:
            engine = BuildEngine(golem_config)
            compiled = engine.build_site()
        except Exception as e:
            report_engine_diagnostics(engine, strict=strict)
            raise click.ClickException(f"Compilation Error: {e}")

        report_engine_diagnostics(engine, strict=strict)

        elapsed = time.perf_counter() - start_time
        if compiled:
            page_word = "page" if len(compiled) == 1 else "pages"
            click.echo(f"Compilation finished. Built {len(compiled)} {page_word} in {elapsed:.2f}s.")
        else:
            click.echo(f"Compilation finished. Built 0 pages (site is up to date) in {elapsed:.2f}s.")

        watch_directories = [
            Path(golem_config.content_dir),
            Path(golem_config.templates_dir),
            Path("themes"),
        ]

        def on_rebuild():
            t0 = time.perf_counter()
            click.echo("Changes detected. Rebuilding static site...")
            try:
                recompiled = engine.build_site()
            except Exception:
                report_engine_diagnostics(engine, strict=strict)
                raise
            report_engine_diagnostics(engine, strict=strict)
            dt = time.perf_counter() - t0
            if recompiled:
                p_word = "page" if len(recompiled) == 1 else "pages"
                click.echo(f"Rebuild finished. Built {len(recompiled)} {p_word} in {dt:.2f}s. Reloading connected tabs...")
            else:
                click.echo(f"Rebuild finished (site is up to date) in {dt:.2f}s.")
            return recompiled

        server = LiveReloadServer(
            public_dir=Path(golem_config.output_dir),
            watch_dir=Path(golem_config.content_dir),
            watch_directories=watch_directories,
            change_detected_func=lambda: bool(engine.staleness_tracker.get_outdated_files(commit=False)),
            rebuild_func=on_rebuild,
            port=port,
            host=host,
            errors_func=lambda: engine.diagnostics,
        )

        bound_port = server.bind() if hasattr(server, "bind") else port
        click.echo(
            f"Ready! Serving '{golem_config.output_dir}' at http://{host}:{bound_port} "
            f"(watching '{golem_config.content_dir}' for changes)"
        )
        click.echo("Press Ctrl+C to stop.")

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

        configured_plugins = list(config.plugins) if config.plugins else []

        plugins_list: list[dict[str, Any]] = []
        seen_names: set[str] = set()

        # 1. Entry points for golem.plugins (both built-in and third-party)
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
            dist_name = getattr(dist, "name", "") if dist else ""
            if dist_name in ("golem", "golem-docs"):
                source = "built-in"
                description = "(built-in)"
            else:
                dist_version = getattr(dist, "version", "") if dist else ""
                dist_desc = f"{dist_name} {dist_version}".strip() if dist_version else f"{dist_name or ep_name}"
                source = "entry_point"
                description = f"(entry_point: {dist_desc})"

            ep_value = getattr(ep, "value", "")
            ep_module = ep_value.split(":")[0] if ep_value else ""
            is_enabled = (
                ep_name in configured_plugins
                or (bool(ep_value) and ep_value in configured_plugins)
                or (bool(ep_module) and ep_module in configured_plugins)
            )

            plugins_list.append(
                {
                    "name": ep_name,
                    "enabled": is_enabled,
                    "source": source,
                    "description": description,
                }
            )
            seen_names.add(ep_name)
            if ep_value:
                seen_names.add(ep_value)
            if ep_module:
                seen_names.add(ep_module)

        # 2. Local plugins in plugins_dir
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

        # 3. Any other custom configured plugins
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
