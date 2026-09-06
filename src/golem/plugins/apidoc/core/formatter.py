from __future__ import annotations

import re
from typing import Any

import asciidocstring
import griffe

from .extractor import get_class_members, get_module_members

# Maximum length (in characters) of an attribute value rendered inline.
# Values longer than this are replaced with a truncated note.
_MAX_INLINE_VALUE_LEN = 80


def _safe_attr_value(attr: griffe.Attribute) -> str:
    """Return a safe, single-line representation of an attribute value for AsciiDoc.

    Long values (e.g. multi-line string constants) are replaced with a
    truncated note so they don't inject AsciiDoc markup into the output.
    """
    raw = str(attr.value) if attr.value is not None else ""
    if not raw:
        return ""
    # Collapse real newlines (shouldn't happen in griffe's expr repr, but be safe)
    single = raw.replace("\n", " ").replace("\r", "")
    if len(single) > _MAX_INLINE_VALUE_LEN:
        preview = single[:_MAX_INLINE_VALUE_LEN].rstrip()
        return f"_{preview}..._ (truncated; see source)"
    return f"`{single}`"


def _offset_headings(text: str, offset: int) -> str:
    """Shift every AsciiDoc section heading in *text* down by *offset* levels.

    This prevents a docstring that opens with ``= Title`` from producing a
    second root-level heading when it is embedded inside a document that
    already has a root heading.

    Only leading ``=`` sequences on their own line are affected; ``==+``
    inside code blocks or description list markers are left alone because
    this is a simple line-start replacement — code blocks are delimited by
    ``----`` and their content lines don't start with ``=``.
    """
    if offset <= 0:
        return text

    def _bump(m: re.Match) -> str:
        return "=" * (len(m.group(1)) + offset) + m.group(2)

    return re.sub(r"^(=+)( )", _bump, text, flags=re.MULTILINE)


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
    style: str | griffe.DocstringStyle | griffe.Parser = "auto",
    heading_offset: int = 0,
) -> str:
    """Convert a docstring into clean AsciiDoc markup using asciidocstring and Griffe.

    Handles composite and union type annotations (e.g. `Union[dict[str, int], list[str]]`,
    `Optional[float]`) and named return structures cleanly via asciidocstring.

    Args:
        docstring: The docstring to convert.
        style: Docstring parsing style (``"google"``, ``"numpy"``, ``"sphinx"``,
            or ``"auto"``).
        heading_offset: Number of heading levels to shift any ``=`` headings
            found in the docstring text.  Use this when embedding a docstring
            inside a document that already has a root heading, so that a
            docstring opening with ``= Title`` doesn't produce a second
            document-root-level heading.
    """
    if not docstring:
        return ""

    if isinstance(docstring, griffe.Docstring):
        doc_obj = docstring
    else:
        doc_obj = griffe.Docstring(str(docstring))

    raw_val = str(doc_obj.value).strip() if doc_obj.value is not None else ""
    if not raw_val:
        return ""

    norm_style = getattr(style, "value", style)
    style_str = str(norm_style).lower() if norm_style is not None else "auto"
    style_lit: Any = style_str if style_str in ("google", "numpy", "sphinx", "auto") else "auto"
    sections = griffe.parse(doc_obj, style_lit)
    result = asciidocstring.griffe_bridge.to_asciidoc(sections)
    if not result.strip() and raw_val:
        result = raw_val

    return _offset_headings(result, heading_offset)


def format_attribute(
    attr: griffe.Attribute,
    heading_level: int = 2,
    docstring_style: str | griffe.DocstringStyle | griffe.Parser = "auto",
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

    doc_text = format_docstring(attr.docstring, style=docstring_style, heading_offset=heading_level)
    if doc_text:
        lines.append("")
        lines.append(doc_text)

    return "\n".join(lines)


def format_function(
    func: griffe.Function,
    heading_level: int = 2,
    docstring_style: str | griffe.DocstringStyle | griffe.Parser = "auto",
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

    doc_text = format_docstring(func.docstring, style=docstring_style, heading_offset=heading_level)
    if doc_text:
        lines.append("")
        lines.append(doc_text)

    return "\n".join(lines)


def format_class(
    cls: griffe.Class,
    depth: str = "all",
    heading_level: int = 2,
    docstring_style: str | griffe.DocstringStyle | griffe.Parser = "auto",
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

    doc_text = format_docstring(cls.docstring, style=docstring_style, heading_offset=heading_level)
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
                val = _safe_attr_value(attr)
                doc = format_docstring(attr.docstring, style=docstring_style) if attr.docstring else ""
                lines.append(f"`{attr.name}`::{ann}")
                lines.append("")
                if doc:
                    lines.append(doc)
                    if val:
                        lines.append("")
                        lines.append(f"Default value: {val}")
                elif val:
                    lines.append(f"Default value: {val}")
                else:
                    lines.append("_(no description)_")
                lines.append("")

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
    docstring_style: str | griffe.DocstringStyle | griffe.Parser = "auto",
    include_private: bool = False,
    include_special: bool = False,
) -> str:
    """Render a Module object to AsciiDoc."""
    title_name = module.path if module.path else module.name
    heading = "=" * max(1, heading_level)
    lines: list[str] = [
        f"{heading} {title_name}",
    ]

    doc_text = format_docstring(module.docstring, style=docstring_style, heading_offset=heading_level)
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
                val = _safe_attr_value(attr)
                doc = format_docstring(attr.docstring, style=docstring_style) if attr.docstring else ""
                # AsciiDoc description list: term on its own line, then a
                # blank line, then the description — prevents the parser from
                # treating inline content as a new block element.
                lines.append(f"`{attr.name}`::{ann}")
                lines.append("")
                if doc:
                    lines.append(doc)
                    if val:
                        lines.append("")
                        lines.append(f"Default value: {val}")
                elif val:
                    lines.append(f"Default value: {val}")
                else:
                    lines.append("_(no description)_")
                lines.append("")

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
