from __future__ import annotations

import logging
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, Any, Sequence

import click

from golem.plugins import hookimpl
from .core import ApiGenOptions, AsciiDocApi

if TYPE_CHECKING:
    from golem.config import GolemConfig

__all__ = [
    "AsciiDocApi",
    "ApiGenOptions",
    "on_asg_created",
    "on_build_start",
    "on_pre_parse",
    "golem_add_subcommands",
    "generate_api_docs",
]

logger = logging.getLogger("golem.plugins.apidoc")

_MACRO_TOKEN_PATTERN = re.compile(
    r"(`[^`\n]+`)|"  # 1: Inline backtick code span
    r"(\\golem:apidoc\[.*?\])|"  # 2: Escaped macro (\golem:apidoc[...])
    r"(golem:apidoc\[(.*?)\])",  # 3: Active macro (group 4 is args)
    re.DOTALL,
)


def _split_verbatim_blocks(content: str) -> list[tuple[bool, str]]:
    """Split AsciiDoc content into tuples of (is_verbatim, text_chunk).

    Verbatim delimited blocks (----, ...., ++++) are protected from macro expansion.
    """
    lines = content.splitlines(keepends=True)
    chunks: list[tuple[bool, str]] = []
    current_chunk: list[str] = []
    in_verbatim = False
    verbatim_delim = ""

    for line in lines:
        stripped = line.strip()
        is_delim = bool(re.match(r"^(-{4,}|\.{4,}|\+{4,})$", stripped))
        if is_delim:
            if in_verbatim and stripped == verbatim_delim:
                current_chunk.append(line)
                chunks.append((True, "".join(current_chunk)))
                current_chunk = []
                in_verbatim = False
                verbatim_delim = ""
                continue
            elif not in_verbatim:
                if current_chunk:
                    chunks.append((False, "".join(current_chunk)))
                    current_chunk = []
                in_verbatim = True
                verbatim_delim = stripped
                current_chunk.append(line)
                continue
        current_chunk.append(line)

    if current_chunk:
        chunks.append((in_verbatim, "".join(current_chunk)))
    return chunks


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


def _extract_plain_text(inlines: Any) -> str:
    """Extract plain string content from nested inlines or dictionaries."""
    if not inlines:
        return ""
    if isinstance(inlines, str):
        return inlines
    if isinstance(inlines, list):
        return "".join(_extract_plain_text(item) for item in inlines)
    if isinstance(inlines, dict):
        if inlines.get("name") == "text":
            return str(inlines.get("value", ""))
        if "value" in inlines and isinstance(inlines["value"], (str, int, float)):
            return str(inlines["value"])
        if "inlines" in inlines:
            return _extract_plain_text(inlines["inlines"])
    return ""


def _create_warning_block(target: str, error_msg: str) -> dict[str, Any]:
    """Create a structured ASG warning admonition block for unresolved symbols."""
    return {
        "name": "admonition",
        "variant": "warning",
        "type": "block",
        "blocks": [
            {
                "name": "paragraph",
                "type": "block",
                "inlines": [
                    {
                        "name": "text",
                        "type": "string",
                        "value": f"Golem ApiDoc: Could not resolve target '{target}': {error_msg}",
                    }
                ],
            }
        ],
    }


def _expand_macro_target(args_str: str) -> list[dict[str, Any]]:
    """Resolve a macro target and return ASG block structures."""
    kwargs = _parse_macro_args(args_str)
    target = kwargs.get("target")
    if not target:
        return []

    depth = kwargs.get("depth", "all")
    style = kwargs.get("style", "auto")
    offset_str = kwargs.get("heading_level_offset") or kwargs.get("heading_offset") or kwargs.get("offset") or "0"
    try:
        heading_offset = int(offset_str)
    except ValueError:
        heading_offset = 0

    options = ApiGenOptions(docstring_style=style, depth=depth)
    api = AsciiDocApi(search_paths=sys.path, options=options)
    try:
        nodes = api.get_asg_nodes(target, depth=depth, heading_level_offset=heading_offset)
        return nodes
    except Exception as e:
        logger.warning("Golem ApiDoc macro error for target '%s': %s", target, e)
        return [_create_warning_block(target, str(e))]


def _process_paragraph_inlines_for_escapes(inlines: list[Any]) -> None:
    """Unescape escaped \\golem:apidoc[...] macros within inline collections in-place."""
    for inline in inlines:
        if isinstance(inline, dict):
            val = inline.get("value")
            if isinstance(val, str) and r"\golem:apidoc[" in val:
                inline["value"] = val.replace(r"\golem:apidoc[", "golem:apidoc[")
            if "inlines" in inline and isinstance(inline["inlines"], list):
                _process_paragraph_inlines_for_escapes(inline["inlines"])


def _has_macro_in_plain_text(inlines: list[Any]) -> bool:
    """Check if any non-code inline text node contains an active golem:apidoc macro."""
    if not inlines:
        return False
    for inline in inlines:
        if not isinstance(inline, dict):
            continue
        # Code spans or verbatim inlines are ignored
        if inline.get("variant") in ("code", "monospace") or inline.get("name") in ("code", "monospace", "literal"):
            continue
        if inline.get("name") == "text":
            val = str(inline.get("value", ""))
            val_no_escapes = val.replace(r"\golem:apidoc[", "")
            if "golem:apidoc[" in val_no_escapes:
                return True
        if "inlines" in inline and isinstance(inline["inlines"], list):
            if _has_macro_in_plain_text(inline["inlines"]):
                return True
    return False


def _splice_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Traverse and splice macro directives into ASG block collections."""
    new_blocks: list[dict[str, Any]] = []

    for block in blocks:
        if not isinstance(block, dict):
            new_blocks.append(block)
            continue

        block_name = block.get("name", "")

        # Verbatim blocks (listing, literal, verse) are protected from macro expansion
        if block_name in ("listing", "literal", "verse"):
            new_blocks.append(block)
            continue

        # Check if block is a block macro (e.g. name is macro / blockMacro or target is apidoc)
        if block_name in ("macro", "blockMacro", "block_macro"):
            target_name = block.get("target") or block.get("name") or ""
            if "golem:apidoc" in str(target_name) or block.get("macro_name") == "golem:apidoc":
                args_str = block.get("arguments") or block.get("value") or ""
                expanded = _expand_macro_target(str(args_str))
                new_blocks.extend(expanded)
                continue

        # Check if block is a paragraph containing golem:apidoc[...]
        if block_name == "paragraph":
            inlines = block.get("inlines", [])

            has_unescaped = _has_macro_in_plain_text(inlines)
            _process_paragraph_inlines_for_escapes(inlines)

            if not has_unescaped:
                new_blocks.append(block)
                continue

            # Active macro in plain text
            raw_text = _extract_plain_text(inlines)
            match = re.search(r"golem:apidoc\[(.*?)\]", raw_text, re.DOTALL)
            if match:
                stripped = raw_text.strip()
                if stripped.startswith("golem:apidoc[") and stripped.endswith("]"):
                    args_str = match.group(1)
                    expanded = _expand_macro_target(args_str)
                    new_blocks.extend(expanded)
                    continue
                else:
                    args_str = match.group(1)
                    expanded = _expand_macro_target(args_str)
                    before_text = raw_text[: match.start()].strip()
                    after_text = raw_text[match.end() :].strip()
                    if before_text:
                        new_blocks.append(
                            {
                                "name": "paragraph",
                                "type": "block",
                                "inlines": [{"name": "text", "type": "string", "value": before_text}],
                            }
                        )
                    new_blocks.extend(expanded)
                    if after_text:
                        new_blocks.append(
                            {
                                "name": "paragraph",
                                "type": "block",
                                "inlines": [{"name": "text", "type": "string", "value": after_text}],
                            }
                        )
                    continue

        # Recursively process nested blocks inside sections, admonitions, sidebars, etc.
        for child_key in ("blocks", "children"):
            child_blocks = block.get(child_key)
            if isinstance(child_blocks, list) and child_blocks:
                block[child_key] = _splice_blocks(child_blocks)

        # Recursively process list items
        items = block.get("items")
        if isinstance(items, list) and items:
            for item in items:
                if isinstance(item, dict):
                    item_blocks = item.get("blocks")
                    if isinstance(item_blocks, list) and item_blocks:
                        item["blocks"] = _splice_blocks(item_blocks)

        new_blocks.append(block)

    return new_blocks


@hookimpl
def on_asg_created(asg: dict[str, Any], doc_path: Path | None = None) -> dict[str, Any]:
    """ASG transform hook: splices golem:apidoc block macros into the document ASG."""
    if not isinstance(asg, dict):
        return asg

    blocks = asg.get("blocks")
    if isinstance(blocks, list) and blocks:
        asg["blocks"] = _splice_blocks(blocks)

    return asg


@hookimpl
def on_pre_parse(raw_content: str) -> str:
    """Pre-parse hook: replaces golem apidoc block macros with rendered AsciiDoc (deprecated fallback).

    .. deprecated::
        Direct AST/ASG macro splicing via `on_asg_created` is preferred.
    """
    if "golem:apidoc[" not in raw_content:
        return raw_content

    chunks = _split_verbatim_blocks(raw_content)
    warned = False

    def _expand_macro(args_str: str) -> str:
        nonlocal warned
        if not warned:
            logger.warning(
                "on_pre_parse macro expansion in golem.plugins.apidoc is deprecated; "
                "use on_asg_created for AST-level ASG macro splicing."
            )
            warned = True

        kwargs = _parse_macro_args(args_str)
        target = kwargs.get("target")
        if not target:
            return f"golem:apidoc[{args_str}]"

        depth = kwargs.get("depth", "all")
        style = kwargs.get("style", "auto")

        options = ApiGenOptions(docstring_style=style, depth=depth)
        api = AsciiDocApi(search_paths=sys.path, options=options)
        try:
            return api.render_symbol(target, depth=depth)
        except Exception as e:
            logger.warning("Golem ApiDoc macro error for target '%s': %s", target, e)
            return f"[WARNING]\n====\nGolem ApiDoc: Could not resolve target '{target}': {e}\n====\n"

    def _replace_in_chunk(text: str) -> str:
        def _sub(match: re.Match[str]) -> str:
            # 1. Inline backtick span -> preserve untouched
            if match.group(1):
                return match.group(1)
            # 2. Escaped macro -> unescape leading backslash
            if match.group(2):
                return match.group(2)[1:]
            # 3. Active macro -> expand
            return _expand_macro(match.group(4))

        return _MACRO_TOKEN_PATTERN.sub(_sub, text)

    result_parts: list[str] = []
    for is_verbatim, chunk_text in chunks:
        if is_verbatim:
            result_parts.append(chunk_text)
        else:
            result_parts.append(_replace_in_chunk(chunk_text))

    return "".join(result_parts)


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
def on_build_start(config: GolemConfig) -> None:
    """Generate API documentation before compilation begins.

    Runs when `config.api_packages` is set.
    Writes AsciiDoc source files into `config.content_dir / config.api_output_dir`
    (defaults to `content_dir/api`) using the `generate_api_docs` core pipeline.
    When `config.api_packages` is empty or `None`, this hook is a no-op.

    On failure, logs a warning and continues unless `config.strict` is `True`,
    in which case the original exception propagates and the build is halted.

    [parameters]
    `config` (GolemConfig):: The active site configuration for this build.

    [raises]
    `Exception`:: Re-raised verbatim when `config.strict` is `True` and API
        doc generation fails. Swallowed with a warning when `config.strict` is `False`.
    """
    if getattr(config, "api_packages", None):
        try:
            dest_dir = Path(config.content_dir) / getattr(config, "api_output_dir", "api")
            generate_api_docs(
                packages=config.api_packages,
                output_dir=dest_dir,
                search_paths=[Path.cwd(), Path("src")] + [Path(p) for p in sys.path if p],
                docstring_style=getattr(config, "api_docstring_style", "auto"),
            )
        except Exception as e:
            logger.warning("Failed to generate API documentation during build: %s", e)
            if getattr(config, "strict", False):
                raise


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
