from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import asciidoctrine
from asciidoctrine.nodes import Admonition, Node, Paragraph, Text
from asciidoctrine.resolver import ASGResolver
import griffe

from .extractor import create_griffe_loader, resolve_symbol
from .formatter import (
    format_attribute,
    format_class,
    format_function,
    format_module,
)


@dataclass
class ApiGenOptions:
    """Configuration options for AsciiDoc API documentation generation."""

    docstring_style: str = "auto"
    depth: str = "all"
    include_private: bool = False
    include_special: bool = False
    heading_level_offset: int = 0
    extra_options: dict[str, str] = field(default_factory=dict)


class AsciiDocApi:
    """Standalone engine for extracting Python package structure and formatting it into AsciiDoc."""

    def __init__(
        self,
        search_paths: Sequence[str | Path] | None = None,
        options: ApiGenOptions | None = None,
    ) -> None:
        self.search_paths: list[str | Path] = list(search_paths) if search_paths is not None else []
        self.options: ApiGenOptions = options or ApiGenOptions()
        self._loader: griffe.GriffeLoader = create_griffe_loader(search_paths=self.search_paths)

    def load_package(self, package_name: str) -> griffe.Module:
        """Load a Python package or module using Griffe."""
        obj = self._loader.load(package_name)
        if not isinstance(obj, griffe.Module):
            raise TypeError(f"Loaded object for '{package_name}' is not a Module: {type(obj).__name__}")
        return obj

    def resolve_symbol(self, symbol_path: str) -> griffe.Object | griffe.Alias:
        """Resolve a fully qualified symbol path to a Griffe object or alias."""
        return resolve_symbol(self._loader, symbol_path)

    def render_symbol(self, symbol_path: str, depth: str | None = None) -> str:
        """Resolve and render any symbol (module, class, function, attribute) to AsciiDoc."""
        target_depth = depth if depth is not None else self.options.depth
        obj = self.resolve_symbol(symbol_path)

        if isinstance(obj, griffe.Alias):
            obj = obj.target

        if isinstance(obj, griffe.Module):
            return self.render_module(obj, depth=target_depth)
        elif isinstance(obj, griffe.Class):
            return self.render_class(obj, depth=target_depth)
        elif isinstance(obj, griffe.Function):
            return self.render_function(obj)
        elif isinstance(obj, griffe.Attribute):
            return self.render_attribute(obj)
        else:
            raise TypeError(f"Unsupported symbol type for rendering: {type(obj).__name__}")

    def render_module(
        self,
        module: griffe.Module,
        depth: str | None = None,
        heading_level: int = 1,
    ) -> str:
        """Render a Griffe Module object to AsciiDoc markup."""
        target_depth = depth if depth is not None else self.options.depth
        level = heading_level + self.options.heading_level_offset
        return format_module(
            module=module,
            depth=target_depth,
            heading_level=level,
            docstring_style=self.options.docstring_style,
            include_private=self.options.include_private,
            include_special=self.options.include_special,
        )

    def render_class(
        self,
        cls: griffe.Class,
        depth: str | None = None,
        heading_level: int = 2,
    ) -> str:
        """Render a Griffe Class object to AsciiDoc markup."""
        target_depth = depth if depth is not None else self.options.depth
        level = heading_level + self.options.heading_level_offset
        return format_class(
            cls=cls,
            depth=target_depth,
            heading_level=level,
            docstring_style=self.options.docstring_style,
            include_private=self.options.include_private,
            include_special=self.options.include_special,
        )

    def render_function(
        self,
        func: griffe.Function,
        heading_level: int = 2,
    ) -> str:
        """Render a Griffe Function object to AsciiDoc markup."""
        level = heading_level + self.options.heading_level_offset
        return format_function(
            func=func,
            heading_level=level,
            docstring_style=self.options.docstring_style,
        )

    def render_attribute(
        self,
        attr: griffe.Attribute,
        heading_level: int = 2,
    ) -> str:
        """Render a Griffe Attribute object to AsciiDoc markup."""
        level = heading_level + self.options.heading_level_offset
        return format_attribute(
            attr=attr,
            heading_level=level,
            docstring_style=self.options.docstring_style,
        )

    def generate_package_docs(self, package_name: str) -> dict[str, str]:
        """Generate full API documentation for a package and all of its submodules.

        Returns a dictionary mapping relative `.adoc` file paths to formatted AsciiDoc document strings.
        """
        root_module = self.load_package(package_name)
        docs: dict[str, str] = {}

        def _walk(mod: griffe.Module) -> None:
            rel_name = mod.path.replace(".", "/")
            adoc_path = f"{rel_name}.adoc"
            docs[adoc_path] = self.render_module(mod, heading_level=1)

            for submod in mod.modules.values():
                if isinstance(submod, griffe.Module):
                    _walk(submod)

        _walk(root_module)
        return docs

    def get_asg_nodes(
        self,
        symbol: str,
        depth: str | None = None,
        heading_level_offset: int = 0,
    ) -> list[Node]:
        """Resolve a Python symbol, render to AsciiDoc markup, and resolve into ASG block nodes.

        [parameters]
        `symbol` (str):: Fully qualified Python symbol path to document.
        `depth` (str | None, optional):: Granularity depth ('all', 'classes', 'methods', 'summary').
        `heading_level_offset` (int, optional):: Additional heading level offset to apply to generated headings.

        [returns]
        `list[Node]`:: Structured ASG block nodes suitable for splicing into a document ASG.
        """
        target_depth = depth if depth is not None else self.options.depth
        orig_offset = self.options.heading_level_offset
        try:
            if heading_level_offset != 0:
                self.options.heading_level_offset = orig_offset + heading_level_offset
            try:
                adoc_markup = self.render_symbol(symbol, depth=target_depth)
                if not adoc_markup.strip():
                    return []
                ast = asciidoctrine.parse_to_ast(adoc_markup)
                doc = ASGResolver(ast).resolve_to_ast(ast)
                return list(doc.blocks)
            except Exception as e:
                return [
                    Admonition(
                        variant="warning",
                        blocks=[Paragraph(inlines=[Text(f"Golem ApiDoc: Could not resolve target '{symbol}': {e}")])],
                    )
                ]
        finally:
            self.options.heading_level_offset = orig_offset
