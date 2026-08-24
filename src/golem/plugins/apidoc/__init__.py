from __future__ import annotations

import logging
from pathlib import Path
import re
import sys
from typing import Sequence

import click

from golem.plugins import hookimpl
from .core import ApiGenOptions, AsciiDocApi

__all__ = ["AsciiDocApi", "ApiGenOptions", "on_pre_parse", "golem_add_subcommands", "generate_api_docs"]

logger = logging.getLogger("golem.plugins.apidoc")

_MACRO_PATTERN = re.compile(r"golem:apidoc\[(.*?)\]", re.DOTALL)


def _parse_macro_args(args_str: str) -> dict[str, str]:
    kwargs: dict[str, str] = {}
    args: list[str] = []
    tokens = re.findall(
        r"(\w+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^,\s\]]+))|(?:\"([^\"]*)\"|'([^']*)'|([^,\s\]]+))",
        args_str,
    )
    for k, v1, v2, v3, p1, p2, p3 in tokens:
        if k:
            kwargs[k] = v1 or v2 or v3
        else:
            val = p1 or p2 or p3
            if val:
                args.append(val)
    if "target" not in kwargs and args:
        kwargs["target"] = args[0]
    return kwargs


@hookimpl
def on_pre_parse(raw_content: str) -> str:
    """Pre-parse hook: replaces golem apidoc block macros with rendered AsciiDoc."""
    if "golem:apidoc[" not in raw_content:
        return raw_content

    def _replace(match: re.Match[str]) -> str:
        args_str = match.group(1)
        kwargs = _parse_macro_args(args_str)
        target = kwargs.get("target")
        if not target:
            return match.group(0)

        depth = kwargs.get("depth", "all")
        style = kwargs.get("style", "auto")

        options = ApiGenOptions(docstring_style=style, depth=depth)
        api = AsciiDocApi(search_paths=sys.path, options=options)
        try:
            return api.render_symbol(target, depth=depth)
        except Exception as e:
            logger.warning("Golem ApiDoc macro error for target '%s': %s", target, e)
            return f"[WARNING]\n====\nGolem ApiDoc: Could not resolve target '{target}': {e}\n====\n"

    return _MACRO_PATTERN.sub(_replace, raw_content)


def generate_api_docs(
    packages: Sequence[str],
    output_dir: Path | str,
    search_paths: Sequence[str | Path] | None = None,
    docstring_style: str = "auto",
) -> dict[str, str]:
    """Generate API documentation files on disk for specified packages."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    options = ApiGenOptions(docstring_style=docstring_style)
    api = AsciiDocApi(search_paths=search_paths or sys.path, options=options)

    all_generated: dict[str, str] = {}
    for pkg in packages:
        pkg_docs = api.generate_package_docs(pkg)
        for rel_file, content in pkg_docs.items():
            dest = out_path / rel_file
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            all_generated[str(dest)] = content

    return all_generated


@hookimpl
def golem_add_subcommands(cli: click.Group) -> None:
    """Register the 'apidoc' subcommand with the Golem CLI."""

    @cli.command("apidoc")
    @click.argument("package", required=False)
    @click.option("--output", "-o", default=None, help="Output directory for generated .adoc files")
    @click.option("--docstring-style", "-s", default="auto", help="Docstring style (google, numpy, sphinx, auto)")
    def apidoc_command(
        package: str | None = None,
        output: str | None = None,
        docstring_style: str = "auto",
    ) -> None:
        """Generate AsciiDoc API reference documentation for Python packages."""
        from golem.config import find_default_config_path, load_config

        config = load_config(find_default_config_path())
        packages_to_build: list[str] = []
        if package:
            packages_to_build.append(package)
        elif config.api_packages:
            packages_to_build.extend(config.api_packages)

        if not packages_to_build:
            click.echo("No package specified and no api_packages configured in golem.toml/pyproject.toml.")
            return

        dest_dir = Path(output) if output else Path(config.content_dir) / config.api_output_dir

        click.echo(f"Generating API documentation for: {', '.join(packages_to_build)} -> {dest_dir}")
        generated = generate_api_docs(
            packages=packages_to_build,
            output_dir=dest_dir,
            search_paths=[Path.cwd(), Path("src")] + [Path(p) for p in sys.path if p],
            docstring_style=docstring_style or config.api_docstring_style,
        )
        click.echo(f"Successfully generated {len(generated)} API documentation file(s).")
