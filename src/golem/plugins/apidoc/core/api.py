from __future__ import annotations

import re
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Literal, Sequence, cast

import asciidocstring
import asciidoctrine
from asciidoctrine.nodes import (
    Admonition,
    Collapsible,
    DescriptionList,
    DescriptionListItem,
    DescriptionListTerm,
    Listing,
    Node,
    Open,
    Paragraph,
    Section,
    Sidebar,
    Span,
    Text,
    Title,
)
import griffe

from .extractor import (
    create_griffe_loader,
    get_class_members,
    get_module_members,
    resolve_symbol,
    set_griffe_context,
    clear_griffe_context,
)
from .formatter import (
    _safe_attr_value,
    format_attribute,
    format_attribute_signature,
    format_class,
    format_class_signature,
    format_function,
    format_function_signature,
    format_module,
)

_HEADING_RE = re.compile(r"^(=+)( )", re.MULTILINE)

# Block types that always carry an example, regardless of any role.
_EXAMPLE_BLOCKS = frozenset({"listing", "example"})

# Dual-coding glyph badges (#19): Griffe kind -> (letter, CSS class, aria-label).
GLYPH_MAP: dict[str, tuple[str, str, str]] = {
    "class": ("C", "glyph-class", "Class"),
    "function": ("F", "glyph-function", "Function"),
    "method": ("M", "glyph-method", "Method"),
    "attribute": ("V", "glyph-constant", "Variable"),
}

# Refinements layered on top of the kind map for classes.
_GLYPH_EXCEPTION = ("X", "glyph-exception", "Exception")
_GLYPH_INTERFACE = ("I", "glyph-interface", "Interface")
_GLYPH_TYPE = ("T", "glyph-type", "Type")

_DECORATOR_RE = re.compile(r"^\s*@([A-Za-z_][\w.]*)", re.MULTILINE)

# Docstring styles golem accepts. Everything except `asciidoc` is delegated to
# asciidocstring's Griffe bridge.
DocstringStyle = Literal["asciidoc", "auto", "google", "numpy", "sphinx"]
_SUPPORTED_STYLES: frozenset[str] = frozenset({"asciidoc", "auto", "google", "numpy", "sphinx"})
# Styles asciidocstring's Griffe bridge accepts. `asciidoc` is native and must not
# be forwarded, so it is deliberately absent.
BridgeStyle = Literal["auto", "google", "numpy", "sphinx"]
_BRIDGE_STYLES: frozenset[str] = frozenset({"auto", "google", "numpy", "sphinx"})
# Block names that carry a deprecation's own text rather than its version label.
_DEPRECATED_LABELS: frozenset[str] = frozenset({"admonition"})

# The aliases golem accepts for each semantic docstring section. Mirrors the set
# asciidocstring recognises, so golem can classify a block the same way it does.
_SECTION_ALIASES: dict[str, str] = {
    "parameters": "parameters",
    "params": "parameters",
    "args": "parameters",
    "arguments": "parameters",
    "parameter": "parameters",
    "attributes": "attributes",
    "attribute": "attributes",
    "attrs": "attributes",
    "returns": "returns",
    "return": "returns",
    "yields": "yields",
    "yield": "yields",
    "receives": "receives",
    "receive": "receives",
    "raises": "raises",
    "raise": "raises",
    "exceptions": "raises",
    "exception": "raises",
    "warns": "warns",
    "warn": "warns",
    "warnings": "warns",
    "warning": "warns",
    "examples": "examples",
    "example": "examples",
    "deprecated": "deprecated",
    "deprecation": "deprecated",
}


def _shift_headings(text: str, offset: int) -> str:
    """Shift every AsciiDoc heading in *text* down by *offset* levels.

    Also pins each shifted heading to an explicit `absolute-level` so a docstring
    opened with `=== Title` cannot produce a second document-root heading when the
    docstring is spliced inside a document that already has a root heading.
    """
    if offset <= 0:
        return text

    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return text

    min_eq = min(len(m.group(1)) for m in matches)

    def _bump(m: re.Match[str]) -> str:
        eq_count = len(m.group(1))
        rel_depth = eq_count - min_eq
        abs_level = min(6, max(1, offset + 1 + rel_depth))
        new_equals = "=" * (eq_count + offset)
        return f"[absolute-level={abs_level}]\n{new_equals}{m.group(2)}"

    return _HEADING_RE.sub(_bump, text)


def _attributes(node: Any) -> dict[str, Any]:
    """Return a node's attribute map, tolerating missing or non-dict values."""
    attributes = getattr(node, "attributes", None)
    return attributes if isinstance(attributes, dict) else {}


def _inline_text(node: Any) -> str:
    """Return the plain text carried by an inline node."""
    if isinstance(node, str):
        return node
    return str(getattr(node, "value", "") or "")


def _node_text(node: Any) -> str:
    """Return the plain text carried by any node, descending into children."""
    if isinstance(node, str):
        return node
    value = getattr(node, "value", None)
    if isinstance(value, str):
        return value
    for collection in (getattr(node, "inlines", None), getattr(node, "terms", None)):
        if collection:
            return "".join(_inline_text(child) for child in collection)
    blocks = getattr(node, "blocks", None)
    if blocks:
        return "\n\n".join(_node_text(child) for child in blocks)
    title = getattr(node, "title", None)
    if title is not None:
        return _node_text(title)
    return ""


def _iter_nodes(node: Any) -> Iterator[Any]:
    """Yield *node* and every descendant node, depth first."""
    if not hasattr(node, "get_child_collections"):
        return
    yield node
    for collection in getattr(node, "get_child_collections")().values():
        for child in collection:
            yield from _iter_nodes(child)


def _semantic_role(node: Any) -> str:
    """Return the semantic section a block represents, or an empty string.

    Mirrors asciidocstring's own resolution order: role, style, first positional
    attribute, then the block title.
    """
    attributes = _attributes(node)
    candidates = [
        attributes.get("role"),
        attributes.get("style"),
        attributes.get("1"),
    ]
    title = getattr(node, "title", None)
    if title is not None:
        candidates.append(_node_text(title))
    for candidate in candidates:
        text = str(candidate or "").strip().lower()
        if text in _SECTION_ALIASES:
            return _SECTION_ALIASES[text]
    return ""


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
        set_griffe_context(module_path=package_name, object_name=package_name)
        try:
            obj = self._loader.load(package_name)
            if not isinstance(obj, griffe.Module):
                raise TypeError(f"Loaded object for '{package_name}' is not a Module: {type(obj).__name__}")
            return obj
        finally:
            clear_griffe_context()

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
        set_griffe_context(module_path=getattr(module, "path", None), object_name=module.name)
        try:
            return format_module(
                module=module,
                depth=target_depth,
                heading_level=level,
                docstring_style=self.options.docstring_style,
                include_private=self.options.include_private,
                include_special=self.options.include_special,
            )
        finally:
            clear_griffe_context()

    def render_class(
        self,
        cls: griffe.Class,
        depth: str | None = None,
        heading_level: int = 2,
    ) -> str:
        """Render a Griffe Class object to AsciiDoc markup."""
        target_depth = depth if depth is not None else self.options.depth
        level = heading_level + self.options.heading_level_offset
        set_griffe_context(module_path=getattr(cls, "path", None), object_name=cls.name)
        try:
            return format_class(
                cls=cls,
                depth=target_depth,
                heading_level=level,
                docstring_style=self.options.docstring_style,
                include_private=self.options.include_private,
                include_special=self.options.include_special,
            )
        finally:
            clear_griffe_context()

    def render_function(
        self,
        func: griffe.Function,
        heading_level: int = 2,
    ) -> str:
        """Render a Griffe Function object to AsciiDoc markup."""
        level = heading_level + self.options.heading_level_offset
        set_griffe_context(module_path=getattr(func, "path", None), object_name=func.name)
        try:
            return format_function(
                func=func,
                heading_level=level,
                docstring_style=self.options.docstring_style,
            )
        finally:
            clear_griffe_context()

    def render_attribute(
        self,
        attr: griffe.Attribute,
        heading_level: int = 2,
    ) -> str:
        """Render a Griffe Attribute object to AsciiDoc markup."""
        level = heading_level + self.options.heading_level_offset
        set_griffe_context(module_path=getattr(attr, "path", None), object_name=attr.name)
        try:
            return format_attribute(
                attr=attr,
                heading_level=level,
                docstring_style=self.options.docstring_style,
            )
        finally:
            clear_griffe_context()

    def generate_package_docs(
        self,
        package_name: str,
        format: str = "macro",
    ) -> dict[str, str]:
        """Generate full API documentation for a package and all of its submodules.

        Returns a dictionary mapping relative `.adoc` file paths to AsciiDoc
        strings. `format` controls the output:
        - "macro" (default): emits a `golem.apidoc::` macro call per module,
          which the ASG pipeline expands (glyphs, pills, source drawers, etc.).
        - "full": emits hand-rolled AsciiDoc with headings/signatures/docstrings,
          suitable for doctests and other tools that don't expand the macro.
        """
        root_module = self.load_package(package_name)
        docs: dict[str, str] = {}

        if format == "macro":

            def _walk_macro(mod: griffe.Module) -> None:
                rel_name = mod.path.replace(".", "/")
                adoc_path = f"{rel_name}.adoc"
                docs[adoc_path] = f"golem.apidoc::{mod.path}[depth=all]\n"
                for submod in mod.modules.values():
                    if isinstance(submod, griffe.Module):
                        _walk_macro(submod)

            _walk_macro(root_module)
            return docs

        def _walk_full(mod: griffe.Module) -> None:
            rel_name = mod.path.replace(".", "/")
            adoc_path = f"{rel_name}.adoc"
            docs[adoc_path] = self.render_module(mod, heading_level=1)
            for submod in mod.modules.values():
                if isinstance(submod, griffe.Module):
                    _walk_full(submod)

        _walk_full(root_module)
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
            set_griffe_context(
                module_path=getattr(obj, "path", None),
                object_name=getattr(obj, "name", symbol),
            )
            try:
                if isinstance(obj, griffe.Module):
                    blocks = self._module_nodes(obj, target_depth, level)
                elif isinstance(obj, griffe.Class):
                    blocks = [self._class_node(obj, target_depth, level)]
                elif isinstance(obj, griffe.Function):
                    blocks = [self._function_node(obj, target_depth, level)]
                elif isinstance(obj, griffe.Attribute):
                    blocks = [self._attribute_node(obj, target_depth, level)]
                else:
                    raise TypeError(f"Unsupported symbol type for ASG construction: {type(obj).__name__}")

                self.ensure_absolute_levels(blocks, base_level=level)
                return blocks
            finally:
                clear_griffe_context()
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
    def _decorator_names(obj: Any) -> set[str]:
        """Best-effort decorator base names.

        ``obj.decorators`` resolves Griffe aliases and raises for decorators
        imported from modules outside the loaded collection (for example
        ``@dataclass`` from ``dataclasses``), so the object's source text is
        used as the fallback.
        """
        names: set[str] = set()
        try:
            for dec in getattr(obj, "decorators", None) or []:
                value = getattr(dec, "value", dec)
                names.add(str(value).rsplit(".", 1)[-1].rstrip("()"))
        except Exception:
            names = set()
        if names:
            return names
        try:
            source = str(getattr(obj, "source", "") or "")
        except Exception:
            return names
        for match in _DECORATOR_RE.finditer(source):
            names.add(match.group(1).rsplit(".", 1)[-1])
        return names

    @staticmethod
    def _base_names(obj: Any) -> set[str]:
        """Best-effort base-class names; never triggers alias resolution."""
        names: set[str] = set()
        try:
            for base in getattr(obj, "bases", None) or []:
                names.add(str(base).rsplit(".", 1)[-1])
        except Exception:
            pass
        return names

    @staticmethod
    def _is_async(obj: Any) -> bool:
        """Report whether a Griffe function is ``async def``.

        Tries labels first and falls back to the source text: ``labels`` resolves
        aliases and can raise for decorated members (see `_decorator_names`), and
        the ``async`` keyword is never aliased.
        """
        try:
            if "async" in set(obj.labels):
                return True
        except Exception:
            pass
        try:
            return bool(re.match(r"\s*async\s+def", str(getattr(obj, "source", "") or "")))
        except Exception:
            return False

    @classmethod
    def _runtime_pills(cls, obj: Any, *, is_member: bool) -> list[dict[str, str | None]]:
        """Runtime qualifier pills from Griffe inspection (#20).

        `@property` is intentionally absent: Griffe models property members as
        Attributes, which render as attribute-list rows without a title row, so
        there is no heading for the pill to attach to.
        """
        decorators = cls._decorator_names(obj)
        name = str(getattr(obj, "name", ""))
        pills: list[dict[str, str | None]] = []
        if is_member and name == "__init__":
            pills.append({"text": "Constructor", "css_class": "pill-runtime", "title": None})
        for label in ("classmethod", "staticmethod"):
            if label in decorators:
                pills.append({"text": label, "css_class": "pill-runtime", "title": None})
        if decorators & {"abstractmethod", "abstractproperty"}:
            pills.append({"text": "abstract", "css_class": "pill-runtime", "title": None})
        if cls._is_async(obj):
            pills.append({"text": "Async", "css_class": "pill-async", "title": None})
        return pills

    @staticmethod
    def _docstring_pills(parsed: asciidocstring.AsciiDocStringDocument | None) -> list[dict[str, str | None]]:
        """Docstring-driven semantic pills from asciidocstring models (#20)."""
        if parsed is None:
            return []
        pills: list[dict[str, str | None]] = []

        version_added = getattr(parsed, "version_added", None)
        version = str(getattr(version_added, "version", "") or "").strip() if version_added else ""
        if version:
            pills.append({"text": f"Stable v{version}+", "css_class": "pill-baseline", "title": None})

        deprecated = getattr(parsed, "deprecated", None)
        if deprecated:
            reason = str(getattr(deprecated, "reason", "") or getattr(deprecated, "description", "") or "").strip()
            pills.append({"text": "Deprecated", "css_class": "pill-deprecated", "title": reason or None})

        if getattr(parsed, "is_experimental", False):
            pills.append({"text": "Experimental", "css_class": "pill-experimental", "title": None})
        return pills

    def _member_pills(
        self,
        obj: Any,
        *,
        is_member: bool,
        parsed: asciidocstring.AsciiDocStringDocument | None = None,
    ) -> list[dict[str, str | None]]:
        """Compute the modifier pills for a function/method member (#20)."""
        return [*self._runtime_pills(obj, is_member=is_member), *self._docstring_pills(parsed)]

    @classmethod
    def _symbol_glyph(cls, obj: Any, *, is_member: bool = False) -> dict[str, str] | None:
        """Map a Griffe object to its dual-coding glyph badge (#19).

        Returns a ``{"letter", "css_class", "label"}`` mapping for the six
        supported kinds, or ``None`` for module-like objects. Classification
        deliberately avoids ``.labels``/``.decorators``: those resolve Griffe
        aliases and raise ``AliasResolutionError`` for decorators imported from
        modules outside the loaded collection (``@dataclass`` being the common
        case).
        """
        kind = getattr(obj, "kind", None)
        kind_value = getattr(kind, "value", str(kind or ""))
        if kind_value == "class":
            bases = cls._base_names(obj)
            decorators = cls._decorator_names(obj)
            if bases & {"Exception", "BaseException"}:
                letter, css_class, label = _GLYPH_EXCEPTION
            elif "Protocol" in bases:
                letter, css_class, label = _GLYPH_INTERFACE
            elif "dataclass" in decorators or "TypedDict" in bases:
                letter, css_class, label = _GLYPH_TYPE
            else:
                letter, css_class, label = GLYPH_MAP["class"]
            return {"letter": letter, "css_class": css_class, "label": label}
        if kind_value == "function":
            letter, css_class, label = GLYPH_MAP["method" if is_member else "function"]
            return {"letter": letter, "css_class": css_class, "label": label}
        if kind_value == "attribute":
            letter, css_class, label = GLYPH_MAP["attribute"]
            return {"letter": letter, "css_class": css_class, "label": label}
        return None

    @staticmethod
    def _source_drawer(func: Any) -> Open | None:
        """Represent a member's raw source as a collapsed-by-default drawer (#24).

        Emits a renamed Open node wrapping a syntax-highlighted Python listing; the
        `source-drawer.html` template supplies the ``<details>``/``<summary>``
        chrome. Returns None when there is no source to show.
        """
        try:
            source = str(getattr(func, "source", "") or "").strip()
        except Exception:
            return None
        if not source:
            return None
        try:
            listing = Listing(inlines=[Text(source)], attributes={"style": "source", "language": "python"})
            drawer = Open(blocks=[listing])
            drawer.name = "source-drawer"
            return drawer
        except Exception:
            return None

    @staticmethod
    def _signature_listing(signature: str, *, aria_label: str = "Method signature") -> Listing:
        """Represent a Python declaration as a typed source listing node.

        Emits an ``apidoc-signature`` node (a renamed Listing) carrying both the
        raw signature text in ``inlines`` and a pre-tokenised HTML rendering in
        ``attributes['signature_html']`` so the Chameleon template can inject
        ``ast-token`` spans without re-parsing. ``aria_label`` is stored on the
        node so the template can emit a symbol-type-specific label (e.g.
        "Class signature" for classes, "Attribute signature" for attributes).
        """
        node = Listing(inlines=[Text(signature)], attributes={"style": "source", "language": "python"})
        node.name = "apidoc-signature"
        node.attributes["signature_html"] = AsciiDocApi._tokenize_signature(signature)
        node.attributes["aria-label"] = aria_label
        return node

    @staticmethod
    def _tokenize_signature(signature: str) -> str:
        """Wrap Python type annotation tokens with <span class="ast-token"> markup.

        Escapes the raw signature for HTML, then walks the string tracking bracket
        depth so that nested generics (List[Dict[str, int]]), callables
        (Callable[[int], str]), and unions (str | None | int) are captured in full
        rather than truncated at the first closing bracket.
        """
        import html as _html

        escaped = _html.escape(signature)
        result: list[str] = []
        i = 0
        n = len(escaped)

        while i < n:
            c = escaped[i]

            # Parameter/return type annotation marker ": " at top level.
            if c == ":" and i + 1 < n and escaped[i + 1] == " ":
                j = i + 2  # skip past ": "
                start = j
                inner_depth = 0
                while j < n:
                    cc = escaped[j]
                    if cc in "([{":
                        inner_depth += 1
                    elif cc in ")]}":
                        inner_depth = max(0, inner_depth - 1)
                    elif cc in ",)= " and inner_depth == 0:
                        break
                    j += 1
                type_name = escaped[start:j].strip()
                if type_name:
                    result.append(': <span class="ast-token">' + type_name + "</span>")
                else:
                    result.append(": ")
                i = j
                continue

            # Return annotation marker "-> " at top level (HTML-escaped as "-&gt; ").
            if c == "-" and escaped[i : i + 5] == "-&gt;" and i + 5 < n and escaped[i + 5] == " ":
                j = i + 6  # skip past "-&gt; "
                start = j
                inner_depth = 0
                while j < n:
                    cc = escaped[j]
                    if cc in "([{":
                        inner_depth += 1
                    elif cc in ")]}":
                        inner_depth = max(0, inner_depth - 1)
                    j += 1
                type_name = escaped[start:j].strip()
                if type_name:
                    result.append('-&gt; <span class="ast-token">' + type_name + "</span>")
                else:
                    result.append("-&gt; ")
                i = j
                continue

            # Regular character — pass through unchanged.
            result.append(c)
            i += 1

        return "".join(result)

    def _docstring_nodes(
        self,
        docstring: griffe.Docstring | None,
        heading_offset: int,
        parsed: asciidocstring.AsciiDocStringDocument | None = None,
    ) -> list[Node]:
        """Convert a Griffe docstring into typed ASG nodes via asciidocstring.

        asciidocstring parses the docstring once and produces both the AsciiDoc ASG
        and the semantic models. Blocks the semantic models recognise (parameters,
        returns, raises, examples, ...) are emitted as typed ASG nodes; every other
        block passes through untouched so authored sub-headings, tables and inline
        markup survive intact.

        `parsed` lets callers that need the semantic models anyway (modifier pills)
        hand in the single parse instead of paying for a second one.
        """
        raw = self._raw_docstring(docstring)
        if not raw:
            return []

        doc = parsed if parsed is not None else self._parse_docstring(raw)
        if doc is None:
            return []

        ast = getattr(doc, "ast", None)
        blocks = list(getattr(ast, "blocks", None) or [])
        if not blocks:
            return []

        nodes: list[Node] = []
        for block in blocks:
            nodes.extend(self._docstring_block_nodes(block, doc, heading_offset))
        nodes.extend(self._docstring_attribute_nodes(doc, heading_offset))
        return nodes

    # ---- docstring parsing -------------------------------------------------

    @staticmethod
    def _raw_docstring(docstring: griffe.Docstring | None) -> str:
        """Return the cleaned raw text of a docstring, or an empty string."""
        if docstring is None:
            return ""
        value = getattr(docstring, "value", None)
        if value is None:
            return ""
        return textwrap.dedent(str(value)).strip()

    def _parse_docstring(self, raw: str) -> asciidocstring.AsciiDocStringDocument | None:
        """Parse raw docstring text into an AsciiDocStringDocument, or None on failure.

        `asciidoc` and `auto` parse the docstring as native AsciiDoc. The remaining
        styles are delegated to asciidocstring's Griffe bridge, which converts the
        Google/NumPy/Sphinx sections back into the same AsciiDoc semantic models so
        every downstream builder sees one uniform representation.
        """
        style = self._docstring_style()
        try:
            if style in ("google", "numpy", "sphinx"):
                return asciidocstring.from_griffe(raw, style=cast(BridgeStyle, style))
            doc = asciidocstring.parse(raw, safe_mode=True)
            if style == "auto" and not self._has_semantic_sections(doc):
                # Native AsciiDoc parsing found nothing structured; the docstring is
                # probably Google/NumPy/Sphinx, so let the bridge retry it.
                try:
                    alternate = asciidocstring.from_griffe(raw, style="auto")
                    if self._has_semantic_sections(alternate):
                        return alternate
                except Exception:
                    pass
            return doc
        except Exception:
            return None

    def _docstring_style(self) -> DocstringStyle:
        """Normalise the configured docstring style to one of the supported tokens."""
        raw = getattr(self.options.docstring_style, "value", self.options.docstring_style)
        style = str(raw).strip().lower() if raw is not None else "auto"
        if style not in _SUPPORTED_STYLES:
            return "auto"
        return cast(DocstringStyle, style)

    @staticmethod
    def _has_semantic_sections(doc: asciidocstring.AsciiDocStringDocument) -> bool:
        """Report whether the parsed docstring yielded any semantic sections."""
        return bool(
            doc.parameters
            or doc.attributes
            or doc.returns
            or doc.yields
            or doc.receives
            or doc.raises
            or doc.warns
            or doc.examples
            or doc.deprecated
        )

    # ---- per-block dispatch -------------------------------------------------

    @classmethod
    def _docstring_block_nodes(
        cls,
        block: Node,
        doc: asciidocstring.AsciiDocStringDocument,
        heading_offset: int,
    ) -> list[Node]:
        """Emit ASG nodes for one top-level docstring block.

        Returns the typed nodes for blocks the semantic models claim, or the block
        itself (shifted onto the host document's heading scale) when unrecognised.
        """
        kind = _semantic_role(block)
        if not kind and getattr(block, "name", "").lower() in _EXAMPLE_BLOCKS:
            # A bare source listing (or a `====` example block) is an example even
            # without an explicit role: asciidocstring classifies it the same way.
            kind = "examples"
        handler = cls._SEMANTIC_BLOCK_HANDLERS.get(kind)
        if handler is None:
            return cls._passthrough_block_nodes(block, heading_offset)
        nodes: list[Node] = getattr(cls, handler)(block, doc, heading_offset)
        return nodes

    @classmethod
    def _passthrough_block_nodes(cls, block: Node, heading_offset: int) -> list[Node]:
        """Emit an unrecognised block verbatim.

        `ensure_absolute_levels` pins any heading it contains onto the host
        document's scale once the docstring has been spliced in, so nothing needs
        to be rewritten here.
        """
        return [block]

    @classmethod
    def _example_blocks_from_section(cls, block: Node, doc: Any, heading_offset: int) -> list[Node]:
        """Emit the listings carried by an examples-role block as sidebar Sidebars."""
        listings = [n for n in _iter_nodes(block) if getattr(n, "name", "").lower() == "listing"]
        sidebars: list[Node] = []
        for listing in listings:
            attributes = getattr(listing, "attributes", None) or {}
            language = str(attributes.get("language") or "python")
            content = "\n".join(_inline_text(i) for i in getattr(listing, "inlines", None) or [])
            if not content:
                content = str(getattr(listing, "value", "") or "")
            example = asciidocstring.DocstringExample(
                content=content,
                language=language,
                is_interactive=content.lstrip().startswith(">>> "),
            )
            sidebars.extend(cls._build_example_sidebars([example], heading_offset))
        return sidebars

    @classmethod
    def _list_blocks_from_section(cls, block: Node, doc: Any, heading_offset: int) -> list[Node]:
        """Emit every list carried by a typed-role block as a DescriptionList.

        Used for parameter/attribute blocks that asciidocstring has already parsed
        into `DocstringParam`/`DocstringAttribute` models.

        Parameters are emitted with tiered disclosure (#17): required parameters
        (no default) in a first description list, optional parameters (with
        default) in a second description list wrapped in a Collapsible node.
        Attributes keep the existing single-list behavior.
        """
        kind = _semantic_role(block)
        model_name = "attributes" if kind == "attributes" else "parameters"
        entries = list(getattr(doc, model_name, None) or [])
        if not entries:
            return []

        # Parameters: tiered disclosure — required first, then optional (#17)
        if kind == "parameters":
            required = [e for e in entries if getattr(e, "default", None) is None]
            optional = [e for e in entries if getattr(e, "default", None) is not None]
            dlists = cls._description_lists(block)
            if not dlists:
                return []
            dlist = dlists[0]
            items = list(getattr(dlist, "items", None) or [])
            # Split items positionally to match the entry split
            req_items = items[: len(required)]
            opt_items = items[len(required) :]
            param_nodes: list[Node] = []
            if required:
                param_nodes = cls._build_parameter_table(req_items, required, heading_offset, tier=1)
            else:
                param_nodes = []
            if optional:
                opt_nodes = cls._build_parameter_table(opt_items, optional, heading_offset, tier=2)
                if opt_nodes:
                    opt_dl = opt_nodes[0]
                    # Wrap optional parameters in Collapsible for progressive disclosure
                    collapsible = Collapsible(
                        title=Title(inlines=[Text("Optional parameters")]),
                        blocks=[opt_dl],
                    )
                    param_nodes.append(collapsible)
            return param_nodes

        # Attributes: single description list (existing behavior)
        attr_nodes: list[Node] = []
        for dlist in cls._description_lists(block):
            attr_nodes.extend(cls._description_list(dlist, entries, heading_offset))
        return attr_nodes

    @classmethod
    def _build_parameter_table(
        cls,
        items: Sequence[Node],
        entries: Sequence[Any],
        heading_offset: int,
        tier: int,
    ) -> list[Node]:
        """Build a parameter table (tier 1 = required, tier 2 = optional)."""
        from asciidoctrine.nodes import Table, TableRow, TableCell

        rows: list[TableRow] = []

        # Header row
        header_cells = [
            TableCell(blocks=[Paragraph(inlines=[Text("Parameter")])]),
            TableCell(blocks=[Paragraph(inlines=[Text("Type")])]),
            TableCell(blocks=[Paragraph(inlines=[Text("Description")])]),
        ]
        rows.append(TableRow(cells=header_cells))

        for item, entry in zip(items, entries):
            name = str(getattr(entry, "name", "") or "")
            type_name = getattr(entry, "type_name", "")

            # Parameter name with required/optional tag
            param_name_parts: list = [Text(name)]
            if getattr(entry, "default", None) is None:
                param_name_parts.append(Span(variant="param-required-tag", inlines=[Text("*required")]))
            else:
                default_val = getattr(entry, "default", None)
                if default_val is not None:
                    param_name_parts.append(Text(f"default: {default_val}"))

            name_cell = TableCell(blocks=[Paragraph(inlines=param_name_parts)])

            # Type cell
            type_cell = TableCell(blocks=[Paragraph(inlines=[Text(type_name)])] if type_name else [])

            # Description cell
            description = cls._description_blocks(item, entry, heading_offset)
            desc_cell = TableCell(blocks=description)

            rows.append(TableRow(cells=[name_cell, type_cell, desc_cell]))

        table = Table(rows=rows)
        return [table]

    @classmethod
    def _description_list_from_items(
        cls,
        dlist: Node,
        items: Sequence[Node],
        entries: Sequence[Any],
        heading_offset: int,
    ) -> list[Node]:
        """Build a DescriptionList from specific items and entry pairs.

        Same pairing logic as `_description_list`, but operates on explicit
        item/entry subsets rather than the full dlist. Used for tiered
        parameter disclosure (#17).
        """
        dlist_items: list[DescriptionListItem] = []
        for item, entry in zip(items, entries):
            name = str(getattr(entry, "name", "") or "")
            type_name = getattr(entry, "type_name", None)
            label = f"{name} ({type_name})" if type_name and name else name or _node_text(item)
            term = DescriptionListTerm(inlines=[Text(label)])
            blocks = cls._description_blocks(item, entry, heading_offset)
            dlist_items.append(DescriptionListItem(terms=[term], blocks=blocks))
        if not dlist_items:
            return []
        return [DescriptionList(items=dlist_items)]

    @classmethod
    def _value_blocks_from_section(cls, block: Node, doc: Any, heading_offset: int) -> list[Node]:
        """Emit a returns/yields/receives/raises/warns-role block from its own items.

        The block's description-list items already carry the parsed description, so
        they are reused verbatim; the semantic model only contributes the cleaned-up
        type name. This matters: re-parsing the model's flattened description text
        would cost a full `asciidoctrine.parse_to_ast()` (Earley) pass per entry.
        """
        kind = _semantic_role(block)
        entries = list(getattr(doc, kind, None) or [])
        warn_like = kind in ("raises", "warns")
        nodes: list[Node] = []
        index = 0
        for dlist in cls._description_lists(block):
            for item in getattr(dlist, "items", None) or []:
                entry = entries[index] if index < len(entries) else None
                index += 1
                description = list(getattr(item, "blocks", None) or [])
                if not description and entry is not None:
                    description = cls._build_paragraph_nodes(
                        str(getattr(entry, "description", "") or "").strip(), heading_offset
                    )
                if warn_like:
                    nodes.extend(cls._raises_nodes(kind, entry, item, description))
                else:
                    nodes.extend(description)
                    nodes.extend(cls._type_listings(cls._type_name(entry, item)))
        return nodes

    @staticmethod
    def _description_lists(block: Node) -> list[Node]:
        """Return every description list inside *block*, including *block* itself."""
        return [n for n in _iter_nodes(block) if getattr(n, "name", "").lower() == "descriptionlist"]

    @staticmethod
    def _type_name(entry: Any, item: Node) -> str:
        """Return the entry's type name, falling back to the item's own term text."""
        type_name = str(getattr(entry, "type_name", None) or "").strip()
        if type_name:
            return type_name
        return _node_text(getattr(item, "terms", [None])[0] if getattr(item, "terms", None) else None).strip()

    @classmethod
    def _type_listings(cls, type_name: str) -> list[Node]:
        """Return a source Listing for a type annotation, if there is one."""
        if not type_name:
            return []
        return [Listing(inlines=[Text(type_name)], attributes={"style": "source", "language": "python"})]

    @staticmethod
    def _raises_nodes(kind: str, entry: Any, item: Node, description: list[Node]) -> list[Node]:
        """Return a labelled exception/warning whose description keeps its markup."""
        name = (
            str(getattr(entry, "type_name", None) or getattr(entry, "name", "") or "").strip()
            if entry is not None
            else _node_text(getattr(item, "terms", [None])[0] if getattr(item, "terms", None) else None).strip()
        )
        label = f"`{name}`" if name else "Exception"
        blocks: list[Node] = [Paragraph(inlines=[Text(label)])]
        blocks.extend(description)
        return [Admonition(variant="warning" if kind == "raises" else "caution", blocks=blocks)]

    @classmethod
    def _deprecated_block_nodes(cls, block: Node, doc: Any, heading_offset: int) -> list[Node]:
        """Emit a deprecated-role block as a deprecation admonition.

        The block's own children are reused so inline markup survives; the model
        only supplies the version.
        """
        deprecation = getattr(doc, "deprecated", None)
        version = str(getattr(deprecation, "version", "") or "").strip() if deprecation else ""
        label = f"Deprecated since {version}" if version else "Deprecated"
        blocks: list[Node] = [Paragraph(inlines=[Text(label)])]
        for child in getattr(block, "blocks", None) or []:
            if getattr(child, "name", "").lower() in _DEPRECATED_LABELS:
                continue
            blocks.append(child)
        return [Admonition(variant="note", blocks=blocks)]

    @classmethod
    def _docstring_attribute_nodes(cls, doc: asciidocstring.AsciiDocStringDocument, heading_offset: int) -> list[Node]:
        """Emit attribute-driven notices (`:versionadded:` and friends).

        These are carried by AttributeEntry nodes, which render to nothing, so the
        typed admonitions are appended once the AST blocks have been walked.
        """
        nodes: list[Node] = []
        if doc.version_added:
            nodes.extend(cls._build_version_added_nodes(doc.version_added, heading_offset))
        for change in doc.version_changed:
            nodes.extend(cls._build_version_added_nodes(change, heading_offset))
        if doc.is_experimental:
            nodes.extend(cls._build_experimental_nodes(None, heading_offset))
        return nodes

    # ---- per-section builders ----------------------------------------------

    @classmethod
    def _build_example_sidebars(cls, examples: Sequence[Any], heading_offset: int) -> list[Node]:
        """Build sidebar-track Sidebar nodes, one per parsed example."""
        sidebars: list[Node] = []
        for example in examples:
            blocks = cls._build_source_nodes(getattr(example, "content", ""), example)
            if not blocks:
                continue
            sidebar = Sidebar(blocks=blocks)
            sidebar.attributes["role"] = "sidebar-track"
            sidebars.append(sidebar)
        return sidebars

    @classmethod
    def _description_list(cls, dlist: Node, entries: Sequence[Any], heading_offset: int) -> list[Node]:
        """Pair a description list's own items with the matching semantic entries.

        The entries are matched positionally, which is exact because asciidocstring
        appends them in document order as it walks the same block.
        """
        items: list[DescriptionListItem] = []
        for index, item in enumerate(getattr(dlist, "items", None) or []):
            entry = entries[index] if index < len(entries) else None
            if entry is None:
                items.append(cls._plain_description_item(item, heading_offset))
                continue
            name = str(getattr(entry, "name", "") or "")
            type_name = getattr(entry, "type_name", None)
            label = f"{name} ({type_name})" if type_name and name else name or _node_text(item)
            term = DescriptionListTerm(inlines=[Text(label)])
            blocks = cls._description_blocks(item, entry, heading_offset)
            items.append(DescriptionListItem(terms=[term], blocks=blocks))
        if not items:
            return []
        return [DescriptionList(items=items)]

    @classmethod
    def _description_blocks(cls, item: Node, entry: Any, heading_offset: int) -> list[Node]:
        """Return the description blocks for one entry.

        Prefers the item's own parsed blocks, which keep inline markup; falls back
        to re-parsing the model's flattened text when the item carries none.
        """
        blocks = list(getattr(item, "blocks", None) or [])
        if blocks:
            return blocks
        description = str(getattr(entry, "description", "") or "").strip()
        if description:
            return cls._build_paragraph_nodes(description, heading_offset)
        default = getattr(entry, "default", None)
        if default is not None:
            return [Paragraph(inlines=[Text(f"Default: `{default}`")])]
        return []

    @classmethod
    def _plain_description_item(cls, item: Node, heading_offset: int) -> DescriptionListItem:
        """Keep a description item that no semantic entry claims, verbatim."""
        return DescriptionListItem(
            terms=list(getattr(item, "terms", None) or []),
            blocks=list(getattr(item, "blocks", None) or []),
        )

    @staticmethod
    def _build_source_nodes(code: str, example: Any) -> list[Node]:
        """Build a source Listing for an example, flagging interactive (>>>) prompts."""
        if not code:
            return []
        language = str(getattr(example, "language", None) or "python")
        listing = Listing(inlines=[Text(code)], attributes={"style": "source", "language": language})
        if getattr(example, "is_interactive", False):
            listing.attributes["role"] = "interactive"
        return [listing]

    @staticmethod
    def _build_paragraph_nodes(text: str, heading_offset: int) -> list[Node]:
        """Build paragraph nodes from text, parsing any AsciiDoc markup it contains."""
        if not text:
            return []
        if heading_offset > 0 and "==" in text:
            text = _shift_headings(text, heading_offset)
        try:
            ast = asciidoctrine.parse_to_ast(text)
            return list(ast.blocks)
        except Exception:
            return [Paragraph(inlines=[Text(text)])]

    @classmethod
    def _build_deprecated_nodes(cls, deprecation: Any, heading_offset: int) -> list[Node]:
        """Build a deprecated admonition with version and description."""
        blocks: list[Node] = []
        version = str(getattr(deprecation, "version", "") or "").strip()
        description = str(getattr(deprecation, "description", "") or "").strip()
        label = "Deprecated"
        if version:
            label += f" since {version}"
        blocks.append(Paragraph(inlines=[Text(label)]))
        if description:
            blocks.extend(cls._build_paragraph_nodes(description, heading_offset))
        return [Admonition(variant="note", blocks=blocks)]

    @classmethod
    def _build_version_added_nodes(cls, version: Any, heading_offset: int) -> list[Node]:
        """Build an 'Added in version X' admonition."""
        number = str(getattr(version, "version", "") or "").strip()
        description = str(getattr(version, "description", "") or "").strip()
        label = f"Added in version {number}" if number else "Added"
        blocks: list[Node] = [Paragraph(inlines=[Text(label)])]
        if description:
            blocks.extend(cls._build_paragraph_nodes(description, heading_offset))
        return [Admonition(variant="note", blocks=blocks)]

    @classmethod
    def _build_experimental_nodes(cls, _value: Any, heading_offset: int) -> list[Node]:
        """Build an 'experimental' admonition."""
        return [
            Admonition(
                variant="note",
                blocks=[Paragraph(inlines=[Text("This feature is experimental.")])],
            )
        ]

    # Handler names keyed by the semantic role of a top-level block. Resolved on the
    # class; every handler takes (block, doc, heading_offset) and returns ASG nodes.
    _SEMANTIC_BLOCK_HANDLERS: ClassVar[dict[str, str]] = {
        "examples": "_example_blocks_from_section",
        "parameters": "_list_blocks_from_section",
        "attributes": "_list_blocks_from_section",
        "returns": "_value_blocks_from_section",
        "yields": "_value_blocks_from_section",
        "receives": "_value_blocks_from_section",
        "raises": "_value_blocks_from_section",
        "warns": "_value_blocks_from_section",
        "deprecated": "_deprecated_block_nodes",
    }

    def _function_node(self, func: griffe.Function, depth: str, level: int, *, is_member: bool = False) -> Section:
        parsed = self._parse_docstring(self._raw_docstring(func.docstring))
        blocks: list[Node] = [self._signature_listing(format_function_signature(func))]
        blocks.extend(self._docstring_nodes(func.docstring, level, parsed=parsed))
        drawer = self._source_drawer(func)
        if drawer is not None:
            blocks.append(drawer)
        section = self._section(func.name, level, blocks)
        if is_member:
            section.attributes["role"] = "member-card"
        glyph = self._symbol_glyph(func, is_member=is_member)
        if glyph is not None:
            section.attributes["glyph"] = glyph
        pills = self._member_pills(func, is_member=is_member, parsed=parsed)
        if pills:
            section.attributes["pills"] = pills
        return section

    def _attribute_node(self, attr: griffe.Attribute, depth: str, level: int) -> Section:
        blocks: list[Node] = [self._signature_listing(format_attribute_signature(attr), aria_label="Attribute signature")]
        blocks.extend(self._docstring_nodes(attr.docstring, level))
        if attr.value is not None:
            blocks.append(Paragraph(inlines=[Text(f"Default value: {_safe_attr_value(attr)}")]))
        section = self._section(attr.name, level, blocks)
        glyph = self._symbol_glyph(attr)
        if glyph is not None:
            section.attributes["glyph"] = glyph
        return section

    def _class_node(self, cls: griffe.Class, depth: str, level: int) -> Section:
        parsed = self._parse_docstring(self._raw_docstring(cls.docstring))
        blocks: list[Node] = [self._signature_listing(format_class_signature(cls), aria_label="Class signature")]
        blocks.extend(self._docstring_nodes(cls.docstring, level, parsed=parsed))
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
            attributes_section = self._section("Attributes", child_level, [DescriptionList(items=items)])
            attributes_section.attributes["role"] = "member-card"
            blocks.append(attributes_section)

        if depth in ("all", "methods"):
            raw_methods = [self._unwrap_member(m) for m in members["methods"]]
            blocks.extend(
                self._function_node(method, depth, child_level, is_member=True)
                for method in raw_methods
                if isinstance(method, griffe.Function)
            )

        if depth != "summary":
            raw_nested = [self._unwrap_member(m) for m in members["nested_classes"]]
            # Attenuate depth for nested classes to prevent runaway recursion:
            # "all" -> "classes" (show structure, not full recursive detail),
            # anything else -> "summary" (just the signature).
            nested_depth = "classes" if depth == "all" else "summary"
            blocks.extend(
                self._class_node(nested_class, nested_depth, child_level)
                for nested_class in raw_nested
                if isinstance(nested_class, griffe.Class)
            )

        section = self._section(cls.name, level, blocks)
        section.attributes["role"] = "doc-card"
        glyph = self._symbol_glyph(cls)
        if glyph is not None:
            section.attributes["glyph"] = glyph
        docstring_pills = self._docstring_pills(parsed)
        if docstring_pills:
            section.attributes["pills"] = docstring_pills
        return section

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
                self._attribute_node(attr, depth, level) for attr in raw_attributes if isinstance(attr, griffe.Attribute)
            )
        if depth in ("all", "classes"):
            raw_classes = [self._unwrap_member(m) for m in members["classes"]]
            blocks.extend(self._class_node(cls, depth, level) for cls in raw_classes if isinstance(cls, griffe.Class))
        if depth in ("all", "functions"):
            raw_functions = [self._unwrap_member(m) for m in members["functions"]]
            blocks.extend(
                self._function_node(func, depth, level) for func in raw_functions if isinstance(func, griffe.Function)
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
                submodules_section = self._section("Submodules", level, [DescriptionList(items=items)])
                submodules_section.attributes["role"] = "member-card"
                blocks.append(submodules_section)

        return blocks
