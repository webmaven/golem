from __future__ import annotations

from typing import Any

import asciidocstring
import griffe

from .extractor import get_class_members, get_module_members


def format_parameters(parameters: griffe.Parameters | list[griffe.Parameter]) -> str:
    """Format Griffe parameters into a valid Python argument list string."""
    parts: list[str] = []
    in_pos_only = False
    in_kw_only = False
    had_var_pos = False

    for param in parameters:
        kind = param.kind
        if kind == griffe.ParameterKind.positional_only:
            in_pos_only = True
        elif in_pos_only:
            parts.append("/")
            in_pos_only = False

        if kind == griffe.ParameterKind.keyword_only and not had_var_pos and not in_kw_only:
            parts.append("*")
            in_kw_only = True

        p_str = ""
        if kind == griffe.ParameterKind.var_positional:
            p_str += "*" + param.name
            had_var_pos = True
        elif kind == griffe.ParameterKind.var_keyword:
            p_str += "**" + param.name
        else:
            p_str += param.name

        if param.annotation is not None:
            p_str += f": {param.annotation}"

        if param.default is not None and kind not in (
            griffe.ParameterKind.var_positional,
            griffe.ParameterKind.var_keyword,
        ):
            p_str += f" = {param.default}"

        parts.append(p_str)

    if in_pos_only:
        parts.append("/")

    return ", ".join(parts)


def format_function_signature(func: griffe.Function) -> str:
    """Format a Griffe Function into its complete Python signature."""
    lines: list[str] = []

    # Decorators
    if hasattr(func, "decorators") and func.decorators:
        for dec in func.decorators:
            lines.append(f"@{dec.value}")

    is_async = "async" in getattr(func, "labels", set()) or getattr(func, "is_async", False)
    prefix = "async def " if is_async else "def "
    params_str = format_parameters(func.parameters)
    returns_str = f" -> {func.returns}" if func.returns is not None else ""

    lines.append(f"{prefix}{func.name}({params_str}){returns_str}:")
    return "\n".join(lines)


def format_class_signature(cls: griffe.Class) -> str:
    """Format a Griffe Class into its Python signature."""
    lines: list[str] = []

    # Decorators
    if hasattr(cls, "decorators") and cls.decorators:
        for dec in cls.decorators:
            lines.append(f"@{dec.value}")

    bases_str = f"({', '.join(str(b) for b in cls.bases)})" if cls.bases else ""
    lines.append(f"class {cls.name}{bases_str}:")
    return "\n".join(lines)


def format_attribute_signature(attr: griffe.Attribute) -> str:
    """Format a Griffe Attribute into a Python declaration."""
    sig = attr.name
    if getattr(attr, "annotation", None) is not None:
        sig += f": {attr.annotation}"
    if getattr(attr, "value", None) is not None:
        sig += f" = {attr.value}"
    return sig


def format_docstring(
    docstring: griffe.Docstring | str | None,
    style: str = "auto",
) -> str:
    """Convert a docstring into clean AsciiDoc markup using asciidocstring and Griffe."""
    if not docstring:
        return ""

    if isinstance(docstring, griffe.Docstring):
        doc_obj = docstring
    else:
        doc_obj = griffe.Docstring(str(docstring))

    try:
        style_lit: Any = style if style in ("google", "numpy", "sphinx", "auto") else "auto"
        sections = griffe.parse(doc_obj, style_lit)
        return asciidocstring.griffe_bridge.to_asciidoc(sections)
    except Exception:
        return str(doc_obj.value).strip()


def format_attribute(
    attr: griffe.Attribute,
    heading_level: int = 2,
    docstring_style: str = "auto",
) -> str:
    """Render an Attribute object to AsciiDoc."""
    heading = "=" * max(1, heading_level)
    lines: list[str] = [
        f"{heading} {attr.name}",
        "",
        "[source,python]",
        "----",
        format_attribute_signature(attr),
        "----",
    ]

    doc_text = format_docstring(attr.docstring, style=docstring_style)
    if doc_text:
        lines.append("")
        lines.append(doc_text)

    return "\n".join(lines)


def format_function(
    func: griffe.Function,
    heading_level: int = 2,
    docstring_style: str = "auto",
) -> str:
    """Render a Function (or method) object to AsciiDoc."""
    heading = "=" * max(1, heading_level)
    lines: list[str] = [
        f"{heading} {func.name}",
        "",
        "[source,python]",
        "----",
        format_function_signature(func),
        "----",
    ]

    doc_text = format_docstring(func.docstring, style=docstring_style)
    if doc_text:
        lines.append("")
        lines.append(doc_text)

    return "\n".join(lines)


def format_class(
    cls: griffe.Class,
    depth: str = "all",
    heading_level: int = 2,
    docstring_style: str = "auto",
    include_private: bool = False,
    include_special: bool = False,
) -> str:
    """Render a Class object to AsciiDoc."""
    heading = "=" * max(1, heading_level)
    lines: list[str] = [
        f"{heading} class {cls.name}",
        "",
        "[source,python]",
        "----",
        format_class_signature(cls),
        "----",
    ]

    doc_text = format_docstring(cls.docstring, style=docstring_style)
    if doc_text:
        lines.append("")
        lines.append(doc_text)

    members = get_class_members(
        cls,
        include_private=include_private,
        include_special=include_special,
    )

    # Attributes
    if members["attributes"] and depth != "summary":
        attr_heading = "=" * (heading_level + 1)
        lines.append("")
        lines.append(f"{attr_heading} Attributes")
        lines.append("")
        for attr in members["attributes"]:
            if isinstance(attr, griffe.Attribute):
                ann = f" ({attr.annotation})" if attr.annotation else ""
                val = f" Defaults to `{attr.value}`." if attr.value else ""
                doc = f" {format_docstring(attr.docstring, style=docstring_style)}" if attr.docstring else ""
                lines.append(f"`{attr.name}`::{ann}{doc}{val}")

    # Methods
    if depth in ("all", "methods"):
        for method in members["methods"]:
            if isinstance(method, griffe.Function):
                lines.append("")
                lines.append(
                    format_function(
                        method,
                        heading_level=heading_level + 1,
                        docstring_style=docstring_style,
                    )
                )

    return "\n".join(lines)


def format_module(
    module: griffe.Module,
    depth: str = "all",
    heading_level: int = 1,
    docstring_style: str = "auto",
    include_private: bool = False,
    include_special: bool = False,
) -> str:
    """Render a Module object to AsciiDoc."""
    title_name = module.path if module.path else module.name
    heading = "=" * max(1, heading_level)
    lines: list[str] = [
        f"{heading} {title_name}",
    ]

    doc_text = format_docstring(module.docstring, style=docstring_style)
    if doc_text:
        lines.append("")
        lines.append(doc_text)

    members = get_module_members(
        module,
        include_private=include_private,
        include_special=include_special,
    )

    # Attributes / Constants
    if members["attributes"] and depth != "summary":
        attr_heading = "=" * (heading_level + 1)
        lines.append("")
        lines.append(f"{attr_heading} Module Attributes")
        lines.append("")
        for attr in members["attributes"]:
            if isinstance(attr, griffe.Attribute):
                ann = f" ({attr.annotation})" if attr.annotation else ""
                val = f" = `{attr.value}`" if attr.value else ""
                doc = f" {format_docstring(attr.docstring, style=docstring_style)}" if attr.docstring else ""
                lines.append(f"`{attr.name}`::{ann}{val}{doc}")

    # Classes
    if depth in ("all", "classes"):
        for cls in members["classes"]:
            if isinstance(cls, griffe.Class):
                lines.append("")
                lines.append(
                    format_class(
                        cls,
                        depth=depth,
                        heading_level=heading_level + 1,
                        docstring_style=docstring_style,
                        include_private=include_private,
                        include_special=include_special,
                    )
                )

    # Functions
    if depth in ("all", "functions"):
        for func in members["functions"]:
            if isinstance(func, griffe.Function):
                lines.append("")
                lines.append(
                    format_function(
                        func,
                        heading_level=heading_level + 1,
                        docstring_style=docstring_style,
                    )
                )

    # Submodules listing
    if members["submodules"] and depth == "all":
        sub_heading = "=" * (heading_level + 1)
        lines.append("")
        lines.append(f"{sub_heading} Submodules")
        lines.append("")
        for submod in members["submodules"]:
            if isinstance(submod, griffe.Module):
                sub_doc = submod.docstring.value.splitlines()[0] if submod.docstring and submod.docstring.value else ""
                lines.append(f"* `{submod.path}`: {sub_doc}")

    return "\n".join(lines)
