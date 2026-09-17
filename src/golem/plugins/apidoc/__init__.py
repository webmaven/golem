from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any, Sequence

from asciidoctrine.nodes import Admonition, Paragraph, Text
import click

from golem.model import AsgTransformer, Node
from golem.plugins import hookimpl
from .core import ApiGenOptions, AsciiDocApi

__all__ = [
    "AsciiDocApi",
    "ApiGenOptions",
    "ApidocMacroTransformer",
    "on_asg_created",
    "golem_add_subcommands",
    "generate_api_docs",
]

logger = logging.getLogger("golem.plugins.apidoc")


class ApidocMacroTransformer(AsgTransformer):
    """AST transformer that splices `golem.apidoc::target[...]` block macros into document ASG."""

    def __init__(self, search_paths: Sequence[str | Path] | None = None) -> None:
        super().__init__()
        self.search_paths: list[str | Path] = list(search_paths) if search_paths is not None else list(sys.path)

    def transform(self, asg: Node) -> Node:
        result = self.visit(asg)
        return result if isinstance(result, Node) else asg

    def generic_visit(self, node: Node, **kwargs: Any) -> Any:
        if getattr(node, "name", None) == "golem.apidoc":
            return self._expand_macro_node(node)
        if getattr(node, "name", None) in (r"\golem.apidoc", "\\golem.apidoc"):
            return self._unescape_macro_node(node)
        return super().generic_visit(node, **kwargs)

    def visit_text(self, node: Node, **kwargs: Any) -> Any:
        if isinstance(node, Text) and r"\golem.apidoc::" in node.value:
            node.value = node.value.replace(r"\golem.apidoc::", "golem.apidoc::")
        return node

    def _unescape_macro_node(self, node: Node) -> list[Node]:
        attrs = getattr(node, "attributes", {}) or {}
        target = attrs.get("target", "")
        other_attrs = [f"{k}={v}" for k, v in attrs.items() if k != "target"]
        attr_str = f"[{','.join(other_attrs)}]" if other_attrs else "[]"
        return [Paragraph(inlines=[Text(f"golem.apidoc::{target}{attr_str}")])]

    def _expand_macro_node(self, node: Node) -> list[Node]:
        attrs = getattr(node, "attributes", {}) or {}
        target = attrs.get("target")
        if not target:
            return []
        target = str(target).strip("'\"")

        depth = attrs.get("depth", "all")
        style = attrs.get("style", "auto")
        offset_str = attrs.get("heading_level_offset") or attrs.get("heading_offset") or attrs.get("offset") or "0"
        try:
            heading_offset = int(offset_str)
        except (ValueError, TypeError):
            heading_offset = 0

        options = ApiGenOptions(docstring_style=style, depth=depth)
        api = AsciiDocApi(search_paths=self.search_paths, options=options)
        try:
            return api.get_asg_nodes(target, depth=depth, heading_level_offset=heading_offset)
        except Exception as e:
            logger.warning("Golem ApiDoc macro error for target '%s': %s", target, e)
            return [
                Admonition(
                    variant="warning",
                    blocks=[Paragraph(inlines=[Text(f"Golem ApiDoc: Could not resolve target '{target}': {e}")])],
                )
            ]


@hookimpl
def on_asg_created(asg: Node, doc_path: Path | None = None) -> Node:
    """ASG transform hook: splices golem.apidoc block macros into the document ASG."""
    if not isinstance(asg, Node):
        return asg
    return ApidocMacroTransformer().transform(asg)


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
