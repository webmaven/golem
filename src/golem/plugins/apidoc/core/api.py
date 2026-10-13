from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import asciidoctrine
from asciidoctrine.nodes import (
    Admonition,
    DescriptionList,
    DescriptionListItem,
    DescriptionListTerm,
    Listing,
    Node,
    Paragraph,
    Section,
    Text,
    Title,
)
from asciidoctrine.resolver import ASGResolver
import griffe

from .extractor import create_griffe_loader, get_class_members, get_module_members, resolve_symbol
from .formatter import (
    _safe_attr_value,
    format_attribute,
    format_attribute_signature,
    format_class,
    format_class_signature,
    format_docstring,
    format_function,
    format_function_signature,
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

    @staticmethod
    def _unwrap_member(member: griffe.Object | griffe.Alias) -> griffe.Object | griffe.Alias:
        """Unwrap a Griffe Alias if its target can be resolved."""
        if isinstance(member, griffe.Alias):
            try:
                return member.target
            except Exception:
                return member
        return member

    @staticmethod
    def ensure_absolute_levels(nodes: Sequence[Node], base_level: int = 2) -> None:
        """Ensure all Section and DiscreteHeading nodes have absolute_level set.

        Recursively traverses `nodes`. If a `Section` or `DiscreteHeading` node does not
        have `absolute_level` set, assigns `base_level` (clamped to 1..6). Child section/heading
        nodes inside have their level set to `min(6, base_level + 1)` and so forth.
        """
        for node in nodes:
            name = getattr(node, "name", None)
            is_heading_node = name in ("section", "heading") or hasattr(node, "absolute_level")
            if is_heading_node:
                curr_abs = getattr(node, "absolute_level", None)
                if curr_abs is None:
                    if hasattr(node, "set_absolute_level"):
                        node.set_absolute_level(min(6, max(1, base_level)))
                    elif hasattr(node, "absolute_level"):
                        node.absolute_level = min(6, max(1, base_level))

            child_blocks = getattr(node, "blocks", None)
            if isinstance(child_blocks, list) and child_blocks:
                effective_level = getattr(node, "absolute_level", None) or base_level
                next_level = min(6, effective_level + 1) if is_heading_node else base_level
                AsciiDocApi.ensure_absolute_levels(child_blocks, base_level=next_level)

            items = getattr(node, "items", None)
            if isinstance(items, list) and items:
                for item in items:
                    item_blocks = getattr(item, "blocks", None)
                    if isinstance(item_blocks, list) and item_blocks:
                        AsciiDocApi.ensure_absolute_levels(item_blocks, base_level=base_level)

    def get_asg_nodes(
        self,
        symbol: str,
        depth: str | None = None,
        heading_level_offset: int = 0,
    ) -> list[Node]:
        """Resolve a Python symbol and construct typed ASG block nodes directly.

        [parameters]
        `symbol` (str):: Fully qualified Python symbol path to document.
        `depth` (str | None, optional):: Granularity depth ('all', 'classes', 'methods', 'summary').
        `heading_level_offset` (int, optional):: Additional heading level offset to apply to generated headings.

        [returns]
        `list[Node]`:: Structured ASG block nodes suitable for splicing into a document ASG.
        """
        try:
            target_depth = depth if depth is not None else self.options.depth
            obj = self.resolve_symbol(symbol)
            obj = self._unwrap_member(obj)

            level = max(1, min(6, 2 + heading_level_offset + self.options.heading_level_offset))
            if isinstance(obj, griffe.Module):
                blocks = self._module_nodes(obj, target_depth, level)
            elif isinstance(obj, griffe.Class):
                blocks = [self._class_node(obj, target_depth, level)]
            elif isinstance(obj, griffe.Function):
                blocks = [self._function_node(obj, level)]
            elif isinstance(obj, griffe.Attribute):
                blocks = [self._attribute_node(obj, level)]
            else:
                raise TypeError(f"Unsupported symbol type for ASG construction: {type(obj).__name__}")

            self.ensure_absolute_levels(blocks, base_level=level)
            return blocks
        except Exception as e:
            return [
                Admonition(
                    variant="warning",
                    blocks=[Paragraph(inlines=[Text(f"Golem ApiDoc: Could not resolve target '{symbol}': {e}")])],
                )
            ]

    @staticmethod
    def _section(title: str, level: int, blocks: Sequence[Node]) -> Section:
        """Build a titled API section at an explicit absolute heading level."""
        return Section(
            level=level,
            title=Title(inlines=[Text(title)]),
            blocks=blocks,
            absolute_level=level,
        )

    @staticmethod
    def _signature_listing(signature: str) -> Listing:
        """Represent a Python declaration as a typed source listing node."""
        return Listing(inlines=[Text(signature)], attributes={"style": "source", "language": "python"})

    def _docstring_nodes(self, docstring: griffe.Docstring | None, heading_offset: int) -> list[Node]:
        """Parse authored docstring markup without reparsing generated API structure."""
        rendered = format_docstring(
            docstring,
            style=self.options.docstring_style,
            heading_offset=heading_offset,
        )
        if not rendered.strip():
            return []
        ast = asciidoctrine.parse_to_ast(rendered)
        return list(ASGResolver(ast).resolve_to_ast(ast).blocks)

    def _function_node(self, func: griffe.Function, level: int) -> Section:
        blocks: list[Node] = [self._signature_listing(format_function_signature(func))]
        blocks.extend(self._docstring_nodes(func.docstring, level))
        return self._section(func.name, level, blocks)

    def _attribute_node(self, attr: griffe.Attribute, level: int) -> Section:
        blocks: list[Node] = [self._signature_listing(format_attribute_signature(attr))]
        blocks.extend(self._docstring_nodes(attr.docstring, level))
        if attr.value is not None:
            blocks.append(Paragraph(inlines=[Text(f"Default value: {_safe_attr_value(attr)}")]))
        return self._section(attr.name, level, blocks)

    def _class_node(self, cls: griffe.Class, depth: str, level: int) -> Section:
        blocks: list[Node] = [self._signature_listing(format_class_signature(cls))]
        blocks.extend(self._docstring_nodes(cls.docstring, level))
        members = get_class_members(
            cls,
            include_private=self.options.include_private,
            include_special=self.options.include_special,
        )
        child_level = min(level + 1, 6)

        raw_attributes = [self._unwrap_member(m) for m in members["attributes"]]
        attributes = [m for m in raw_attributes if isinstance(m, griffe.Attribute)]
        if attributes and depth != "summary":
            items: list[DescriptionListItem] = []
            for attr in attributes:
                annotation = f" ({attr.annotation})" if attr.annotation else ""
                term = DescriptionListTerm(inlines=[Text(f"{attr.name}{annotation}")])
                description = self._docstring_nodes(attr.docstring, child_level)
                if attr.value is not None:
                    value = _safe_attr_value(attr)
                    description.append(Paragraph(inlines=[Text(f"Default value: {value}")]))
                elif not description:
                    description = [Paragraph(inlines=[Text("(no description)")])]
                items.append(DescriptionListItem(terms=[term], blocks=description))
            blocks.append(self._section("Attributes", child_level, [DescriptionList(items=items)]))

        if depth in ("all", "methods"):
            raw_methods = [self._unwrap_member(m) for m in members["methods"]]
            blocks.extend(
                self._function_node(method, child_level)
                for method in raw_methods
                if isinstance(method, griffe.Function)
            )

        if depth != "summary":
            raw_nested = [self._unwrap_member(m) for m in members["nested_classes"]]
            blocks.extend(
                self._class_node(nested_class, depth, child_level)
                for nested_class in raw_nested
                if isinstance(nested_class, griffe.Class)
            )

        return self._section(f"class {cls.name}", level, blocks)

    def _module_nodes(self, module: griffe.Module, depth: str, level: int) -> list[Node]:
        blocks = self._docstring_nodes(module.docstring, max(0, level - 1))
        members = get_module_members(
            module,
            include_private=self.options.include_private,
            include_special=self.options.include_special,
        )

        raw_attributes = [self._unwrap_member(m) for m in members["attributes"]]
        if depth != "summary":
            blocks.extend(
                self._attribute_node(attr, level) for attr in raw_attributes if isinstance(attr, griffe.Attribute)
            )
        if depth in ("all", "classes"):
            raw_classes = [self._unwrap_member(m) for m in members["classes"]]
            blocks.extend(self._class_node(cls, depth, level) for cls in raw_classes if isinstance(cls, griffe.Class))
        if depth in ("all", "functions"):
            raw_functions = [self._unwrap_member(m) for m in members["functions"]]
            blocks.extend(
                self._function_node(func, level) for func in raw_functions if isinstance(func, griffe.Function)
            )

        if depth == "all":
            raw_submodules = [self._unwrap_member(m) for m in members["submodules"]]
            submodules = [mod for mod in raw_submodules if isinstance(mod, griffe.Module)]
            if submodules:
                items = []
                for submodule in submodules:
                    description = (
                        submodule.docstring.value.splitlines()[0] if submodule.docstring and submodule.docstring.value else ""
                    )
                    items.append(
                        DescriptionListItem(
                            terms=[DescriptionListTerm(inlines=[Text(submodule.path)])],
                            blocks=[Paragraph(inlines=[Text(description)])] if description else [],
                        )
                    )
                blocks.append(self._section("Submodules", level, [DescriptionList(items=items)]))

        return blocks
