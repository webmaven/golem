"""Orchestrate incremental Directed Acyclic Graph (DAG) compilation, caching, and static site generation for Golem.

== DAG Compilation Architecture

Golem models documentation projects as a Directed Acyclic Graph (DAG) where nodes represent
source documents (`.adoc`), partials (`_*.adoc`), and layout templates, while directed edges
represent file inclusions (`include::...[]`) and structural dependencies.

== Cache Invalidation Strategies

Incremental rebuilds track content digests and filesystem timestamps to avoid redundant compilations:

Direct Invalidation:: If a file's SHA-256 digest on disk differs from its cached hash, the document
is flagged as directly modified.
Reverse Dependency Propagation:: When an included partial or child document changes, the engine
traverses the reverse dependency graph to mark all ancestor documents as outdated.
Template & Configuration Invalidation:: Modifications to global configuration (`golem.toml`) or
master layout templates (`skeleton.pt`, `page.pt`, `layout.pt`) trigger full-site rebuilds.
Modifications to granular component templates only invalidate documents containing matching ASG node types.
Atomic Persistence & Locking:: Cache records are written atomically using a temporary file replacement
strategy and cross-process advisory locks (`filelock.FileLock`) on a dedicated lockfile to prevent corruption
during concurrent builds.

== Build Pipeline Lifecycle

The compilation pipeline proceeds through sequential phases:

1. Stale Detection: Scans `content_dir` for `.adoc` files, purges deleted cache entries, and identifies outdated documents.
2. Static Asset Synchronization: Copies package theme, user theme, and custom static directory assets into `output_dir / "static"`.
3. Pre-Parse Hook Execution: Triggers registered `on_pre_parse` plugin hooks on raw source text.
4. AST Parsing & Hook Execution: Parses source documents into ASTs via `asciidoctrine` and executes `on_ast_created` hooks.
5. ASG Resolution & Hook Execution: Resolves ASTs into Abstract Semantic Graphs (ASG) and executes `on_asg_created` hooks.
6. Body & Table of Contents Rendering: Evaluates ASG nodes into HTML body content and generates structural table-of-contents HTML.
7. Navigation & Pagination Assembly: Discovers site navigation trees and calculates page-specific sequential pagination links.
8. Template Context Framing & Post-Render Hooks: Executes `on_template_context` hooks, compiles the complete HTML page via Chameleon templates (`PageCompiler`), and executes `on_post_render` hooks.
9. Disk Output & Cache Update: Writes compiled HTML files to `output_dir` and updates content hashes and include dependencies in the cache.
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
import sys
from typing import Any

import asciidoctrine
from asciidoctrine.nodes import Document, Node
from asciidoctrine.resolver import ASGResolver
import click
from golem.assets import sync_static_assets
from golem.cache import BuildCache
from golem.config import GolemConfig
from golem.diagnostics import Diagnostic
from golem.metadata import (
    clean_index_url,
    extract_metadata_from_doc,
)
from golem.navigation import NavigationBuilder
from golem.plugins import get_plugin_manager
from golem.renderer import (
    collect_node_types,
    generate_toc_html,
    render_body,
)
from golem.staleness import StalenessTracker, is_partial
from golem.templates import PageCompiler

__all__ = ["BuildEngine", "GolemEngine"]


def _invoke_doc_hook(impl: Any, arg_name: str, arg_val: Any, doc_path: Path) -> Any:
    """Invoke document hook implementation with Pluggy argument filtering."""
    hook_kwargs: dict[str, Any] = {arg_name: arg_val}
    has_doc_path = "doc_path" in getattr(impl, "argnames", ()) or "doc_path" in getattr(impl, "kwargnames", ())
    if not has_doc_path:
        fn = getattr(impl, "function", None)
        code = getattr(fn, "__code__", None)
        if code and (code.co_flags & inspect.CO_VARKEYWORDS):
            has_doc_path = True
        elif fn is not None and not code:
            try:
                sig = inspect.signature(fn)
                has_doc_path = "doc_path" in sig.parameters or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                )
            except (ValueError, TypeError):
                pass

    if has_doc_path:
        hook_kwargs["doc_path"] = doc_path
    return impl.function(**hook_kwargs)


class BuildEngine:
    """Incremental DAG compilation engine for Golem static site builds.

    Manages the end-to-end documentation compilation lifecycle, including dependency
    graph tracking, SHA-256 caching, reverse invalidation propagation, static asset
    synchronization, navigation discovery, and Chameleon template page compilation.

    [attributes]
    `config` (GolemConfig):: Resolved site configuration and build options.
    `content_dir` (Path):: Resolved absolute path to the source content directory.
    `config_path` (Path):: Path to the active `golem.toml` or `pyproject.toml` file.
    `cache_file` (Path):: Path to the JSON cache storage file.
    `cache` (BuildCache):: DAG cache database and file digest tracker instance.
    `staleness_tracker` (StalenessTracker):: Staleness tracker and DAG dependency analyzer.
    `compiler` (PageCompiler):: Page template compiler instance.
    `nav_builder` (NavigationBuilder):: Hierarchical navigation builder and pagination generator.
    `diagnostics` (list[Diagnostic]):: Diagnostic entries captured during compilation.
    `pm` (pluggy.PluginManager):: Plugin manager instance for build lifecycle hooks.

    === Examples

    [source,python]
    ----
    >>> from golem.config import GolemConfig
    >>> from golem.engine import BuildEngine
    >>> from pathlib import Path
    >>> config = GolemConfig(content_dir="content", output_dir="dist")
    >>> engine = BuildEngine(config, cache_file=Path("cache.json"))
    >>> isinstance(engine.cache.data, dict)
    True
    ----
    """

    def __init__(self, config: GolemConfig, cache_file: Path | None = None) -> None:
        """Initialize the build engine with configuration and cache storage.

        Resolves content and configuration paths, loads existing cache records,
        initializes the page template compiler, and activates registered plugins.

        [parameters]
        `config` (GolemConfig):: Site configuration specifying directories, theme, and build parameters.
        `cache_file` (Path | None, optional):: Explicit path to the DAG cache file. Defaults to `<content_dir>/../.golem/cache.json`.
        """
        self.config = config
        self.content_dir = Path(config.content_dir).resolve()
        self.config_path = Path(config.config_path) if config.config_path else Path("golem.toml")
        self.cache_file = cache_file or Path(config.content_dir).parent / ".golem" / "cache.json"
        self.cache = BuildCache(self.cache_file)

        # Load Pluggy Plugin Manager
        plugins_dir = Path(getattr(config, "plugins_dir", "plugins"))
        self.pm = get_plugin_manager(config=config, plugins_dir=plugins_dir)
        asg_spec = getattr(getattr(self.pm.hook, "on_asg_created", None), "spec", None)
        if asg_spec and "doc_path" not in asg_spec.argnames:
            asg_spec.argnames = (*asg_spec.argnames, "doc_path")

        self.staleness_tracker = StalenessTracker(
            config=self.config,
            cache=self.cache,
            content_dir=self.content_dir,
            plugin_manager=self.pm,
            config_path=self.config_path,
        )
        self.compiler = PageCompiler(config)
        self.nav_builder = NavigationBuilder(
            self.config,
            self.content_dir,
            lambda p: is_partial(p, self.content_dir),
            self.get_file_metadata,
        )
        self.diagnostics: list[Diagnostic] = []
        self._nav_tree_cache: list[dict[str, Any]] | None = None

    def get_file_metadata(self, path: Path) -> dict[str, Any]:
        """Retrieve cached or parsed document metadata for an AsciiDoc file.

        Returns cached metadata if the file's SHA-256 digest is unchanged. If the
        file is modified or uncached, extracts fresh metadata from disk and updates
        the cache record.

        [parameters]
        `path` (Path):: Path to the target AsciiDoc document.

        [returns]
        `dict[str, Any]`:: Dictionary containing `"title"`, `"nav_title"`, `"nav_order"`, `"has_toc"`, `"page_class"`, `"body_class"`, `"content_class"`, and `"page_role"` keys.
        """
        p_abs = str(path.resolve())
        current_hash = self.cache.get_sha256(path)
        cached_hash = self.cache.data.get("files", {}).get(p_abs)
        cached_meta = self.cache.data.get("metadata", {}).get(p_abs)

        if cached_meta is not None and cached_hash == current_hash and current_hash != "":
            return cached_meta

        meta = extract_metadata_from_doc(path)
        self.cache.data.setdefault("metadata", {})[p_abs] = meta
        if current_hash:
            self.cache.data.setdefault("files", {})[p_abs] = current_hash
        return meta

    def _generate_canonical_link(self, rel_path: Path | str) -> str:
        """Generate a canonical relative HTML URL path for a document.

        Converts a content relative path to its corresponding `.html` target URL
        and normalizes `index.html` suffixes to directory-style clean URLs via
        `clean_index_url()`.

        [parameters]
        `rel_path` (Path | str):: Document path relative to `content_dir`.

        [returns]
        `str`:: Normalized canonical URL string.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        assert engine._generate_canonical_link("guides/index.adoc") == "guides/"
        assert engine._generate_canonical_link("about.adoc") == "about.html"
        ----
        """
        p = Path(rel_path)
        return clean_index_url(p.with_suffix(".html").as_posix())

    def _get_cached_nav_tree(self) -> list[dict[str, Any]]:
        """Return nav tree, computing once per build cycle.

        The cache is set to `None` at the start of `build_site()` and populated
        on the first call, preventing redundant filesystem scans per compiled page.

        [returns]
        `list[dict[str, Any]]`:: Hierarchical list of navigation item dictionaries.
        """
        if not hasattr(self, "_nav_tree_cache") or self._nav_tree_cache is None:
            self._nav_tree_cache = self.nav_builder.discover_navigation()
        return self._nav_tree_cache

    def build_site(self) -> list[Path]:
        """Orchestrate the incremental compilation pipeline for outdated AsciiDoc documents.

        Executes the complete documentation compilation lifecycle:
        1. Generates automated API reference documentation via `golem.plugins.apidoc` if `config.api_packages` is configured.
        2. Identifies stale or modified documents via `staleness_tracker.get_outdated_files()`.
        3. Synchronizes static assets into the output directory via `sync_static_assets()`.
        4. Compiles each outdated document through sequential AST parsing (`asciidoctrine`), ASG semantic resolution (`ASGResolver`), body rendering (`render_body`), navigation and TOC generation, and Chameleon template layout compilation (`PageCompiler`).
        5. Executes plugin hooks (`on_pre_parse`, `on_ast_created`, `on_asg_created`, `on_template_context`, `on_post_render`) across each lifecycle phase.
        6. Writes compiled HTML files to disk and updates the DAG cache via `staleness_tracker.update_cache_for_file()`.

        [returns]
        `list[Path]`:: List of output `Path` objects for all compiled HTML documents.

        [raises]
        `Exception`:: If compilation fails for any document while `config.strict` is `True`.

        === Examples

        [source,python]
        ----
        from golem.config import GolemConfig
        from golem.engine import BuildEngine

        config = GolemConfig(content_dir="content", output_dir="dist")
        engine = BuildEngine(config)
        compiled_pages = engine.build_site()
        ----
        """
        self.diagnostics = []
        self._nav_tree_cache = None
        compiled_files = []

        # Automated API doc generation when api_packages is configured
        if getattr(self.config, "api_packages", None):
            try:
                from golem.plugins.apidoc import generate_api_docs

                dest_dir = self.content_dir / getattr(self.config, "api_output_dir", "api")
                generate_api_docs(
                    packages=self.config.api_packages,
                    output_dir=dest_dir,
                    search_paths=[Path.cwd(), Path("src")] + [Path(p) for p in sys.path if p],
                    docstring_style=getattr(self.config, "api_docstring_style", "auto"),
                )
            except Exception as e:
                logging.warning(f"Failed to generate API documentation during build: {e}")
                if getattr(self.config, "strict", False):
                    raise

        outdated = self.staleness_tracker.get_outdated_files()

        all_docs = (
            [f for f in self.content_dir.glob("**/*.adoc") if not is_partial(f, self.content_dir)]
            if self.content_dir.exists()
            else []
        )
        to_build = (
            {f for f in outdated if not is_partial(f, self.content_dir)}
            if (outdated or self.cache.data["files"])
            else set(all_docs)
        )

        def _get_build_priority(doc_p: Path) -> tuple[int, str]:
            meta = self.get_file_metadata(doc_p)
            role = (meta.get("page_role") or "").strip().lower()
            # Compile aggregator pages (index, glossary) after content pages
            is_aggregator = 1 if role in ("index", "glossary") else 0
            return (is_aggregator, str(doc_p))

        sorted_to_build = sorted(to_build, key=_get_build_priority)

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        sync_static_assets(self.config, self.content_dir, Path(self.config.output_dir))

        search_paths = self.staleness_tracker._get_template_search_paths()

        for doc_path in sorted_to_build:
            if is_partial(doc_path, self.content_dir):
                continue
            try:
                with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

                # Trigger pre-parse hooks sequentially (chain modifications)
                _pre_parse_modifiers: list[str] = []
                for impl in self.pm.hook.on_pre_parse.get_hookimpls():
                    try:
                        result = impl.function(raw_content=content)
                    except Exception as e:
                        logging.warning(
                            "[Plugin] %s raised an exception in on_pre_parse for %s: %s",
                            impl.plugin_name,
                            doc_path.name,
                            e,
                        )
                        continue
                    if isinstance(result, str) and result != content:
                        _pre_parse_modifiers.append(impl.plugin_name or str(impl.function))
                        content = result
                if len(_pre_parse_modifiers) > 1:
                    logging.warning(
                        "[Plugin] Multiple plugins modified raw_content in on_pre_parse for %s: %s. "
                        "The final result depends on their order in config.plugins. "
                        "Consider whether your transforms are additive.",
                        doc_path.name,
                        _pre_parse_modifiers,
                    )

                # 1. Parse using asciidoctrine
                ast: Document = asciidoctrine.parse_to_ast(content, base_dir=str(doc_path.parent))

                # Trigger AST hooks sequentially (chain modifications)
                _ast_modifiers: list[str] = []
                for impl in self.pm.hook.on_ast_created.get_hookimpls():
                    try:
                        result = impl.function(ast=ast)
                    except Exception as e:
                        logging.warning(
                            "[Plugin] %s raised an exception in on_ast_created for %s: %s",
                            impl.plugin_name,
                            doc_path.name,
                            e,
                        )
                        continue
                    if isinstance(result, Document) and result is not ast:
                        _ast_modifiers.append(impl.plugin_name or str(impl.function))
                        ast = result
                if len(_ast_modifiers) > 1:
                    logging.warning(
                        "[Plugin] Multiple plugins modified ast in on_ast_created for %s: %s. "
                        "The final result depends on their order in config.plugins. "
                        "Consider whether your transforms are additive.",
                        doc_path.name,
                        _ast_modifiers,
                    )

                # 2. Resolve AST to ASG
                resolver = ASGResolver(ast)
                asg: Node = resolver.resolve_to_ast(ast)

                if hasattr(resolver, "warnings") and resolver.warnings:
                    for warn in resolver.warnings:
                        warn_diag = Diagnostic.from_resolver_warning(warn, file=str(doc_path), content=content)
                        self.diagnostics.append(warn_diag)

                # Trigger ASG hooks sequentially (chain modifications)
                _asg_modifiers: list[str] = []
                for impl in self.pm.hook.on_asg_created.get_hookimpls():
                    try:
                        result = _invoke_doc_hook(impl, "asg", asg, doc_path)
                    except Exception as e:
                        logging.warning(
                            "[Plugin] %s raised an exception in on_asg_created for %s: %s",
                            impl.plugin_name,
                            doc_path.name,
                            e,
                        )
                        continue
                    if isinstance(result, Node) and result is not asg:
                        _asg_modifiers.append(impl.plugin_name or str(impl.function))
                        asg = result
                if len(_asg_modifiers) > 1:
                    logging.warning(
                        "[Plugin] Multiple plugins modified asg in on_asg_created for %s: %s. "
                        "The final result depends on their order in config.plugins. "
                        "Consider whether your transforms are additive.",
                        doc_path.name,
                        _asg_modifiers,
                    )

                page_node_types = collect_node_types(asg)

                # 3. Render body using Golem's ASG visitor
                body_content = render_body(asg, search_paths=search_paths)

                # Extract title for layout framing from typed Document node
                title_str = ""
                header = getattr(asg, "header", None)
                if header and getattr(header, "title", None):
                    t = header.title
                    if hasattr(t, "inlines") and t.inlines:
                        title_str = "".join(getattr(n, "value", "") if hasattr(n, "value") else str(n) for n in t.inlines)
                    elif isinstance(t, list) and t:
                        title_str = getattr(t[0], "value", "") if hasattr(t[0], "value") else str(t[0])
                    elif isinstance(t, str):
                        title_str = t
                if not title_str and hasattr(asg, "blocks"):
                    # Fall back to first section title
                    for block in getattr(asg, "blocks", None) or []:
                        if getattr(block, "name", None) in ("section", "title") and getattr(block, "title", None):
                            t = block.title
                            if hasattr(t, "inlines"):
                                title_str = "".join(
                                    getattr(n, "value", "") if hasattr(n, "value") else str(n) for n in t.inlines
                                )
                            elif isinstance(t, list) and t:
                                title_str = getattr(t[0], "value", "") if hasattr(t[0], "value") else str(t[0])
                            elif isinstance(t, str):
                                title_str = t
                            break

                if not title_str:
                    title_str = getattr(asg, "title", "") if not isinstance(getattr(asg, "title", None), (dict, list)) else ""
                if not title_str:
                    title_str = "Golem Doc"

                # 4. Compile layout via Chameleon templates
                toc_html = generate_toc_html(asg)

                # Generate dynamic navigation HTML and chapter pagination for this page
                rel_path = doc_path.relative_to(self.content_dir)
                _nav_tree = self._get_cached_nav_tree()
                nav_html = self.nav_builder.generate_nav_html(current_rel_path=rel_path, nav_tree=_nav_tree)
                prev_page, next_page = self.nav_builder.get_page_pagination(current_rel_path=rel_path, nav_tree=_nav_tree)

                doc_meta = self.get_file_metadata(doc_path)
                page_class = doc_meta.get("page_class", "")
                body_class = doc_meta.get("body_class", "")
                content_class = doc_meta.get("content_class", "")

                asg_attrs: dict[str, Any] = {}
                attributes = getattr(asg, "attributes", None)
                if attributes and isinstance(attributes, dict):
                    asg_attrs = attributes
                else:
                    header = getattr(asg, "header", None)
                    header_attrs = getattr(header, "attributes", None) if header else None
                    if header_attrs and isinstance(header_attrs, dict):
                        asg_attrs = header_attrs

                if not body_class:
                    body_class = asg_attrs.get("body_class") or asg_attrs.get("body-class") or asg_attrs.get("bodyclass") or ""
                if not page_class:
                    page_class = asg_attrs.get("page_class") or asg_attrs.get("page-class") or asg_attrs.get("pageclass") or ""
                if not content_class:
                    content_class = (
                        asg_attrs.get("content_class") or asg_attrs.get("content-class") or asg_attrs.get("contentclass") or ""
                    )

                resolved_body_class = (body_class or page_class or "").strip()
                resolved_content_class = (content_class or "").strip()

                page_role = (
                    asg_attrs.get("page-role")
                    or asg_attrs.get("page_role")
                    or asg_attrs.get("role")
                    or (doc_meta.get("page_role") if doc_meta else None)
                )

                context_dict: dict[str, Any] = {
                    "title": title_str,
                    "body_html": body_content,
                    "toc_html": toc_html,
                    "nav_html": nav_html,
                    "nav_tree": _nav_tree,
                    "current_path": str(rel_path),
                    "prev_page": prev_page,
                    "next_page": next_page,
                    "body_class": resolved_body_class,
                    "content_class": resolved_content_class,
                    "doc_attributes": asg_attrs,
                }
                if page_role:
                    context_dict["page_role"] = page_role

                # Trigger on_template_context hooks sequentially (chain modifications)
                for impl in self.pm.hook.on_template_context.get_hookimpls():
                    try:
                        result = _invoke_doc_hook(impl, "context", context_dict, doc_path)
                    except Exception as e:
                        logging.warning(
                            "[Plugin] %s raised an exception in on_template_context for %s: %s",
                            impl.plugin_name,
                            doc_path.name,
                            e,
                        )
                        if getattr(self.config, "strict", False):
                            raise
                        continue
                    if isinstance(result, dict):
                        context_dict.update(result)

                final_html = self.compiler.compile_page(**context_dict)

                # Trigger post-render hooks sequentially (chain modifications)
                _post_render_modifiers: list[str] = []
                for impl in self.pm.hook.on_post_render.get_hookimpls():
                    try:
                        result = impl.function(html_content=final_html)
                    except Exception as e:
                        logging.warning(
                            "[Plugin] %s raised an exception in on_post_render for %s: %s",
                            impl.plugin_name,
                            doc_path.name,
                            e,
                        )
                        continue
                    if isinstance(result, str) and result != final_html:
                        _post_render_modifiers.append(impl.plugin_name or str(impl.function))
                        final_html = result
                if len(_post_render_modifiers) > 1:
                    logging.warning(
                        "[Plugin] Multiple plugins modified html_content in on_post_render for %s: %s. "
                        "The final result depends on their order in config.plugins. "
                        "Consider whether your transforms are additive.",
                        doc_path.name,
                        _post_render_modifiers,
                    )

                # 5. Resolve correct output file path
                out_path = output_dir / rel_path.with_suffix(".html")
                out_path.parent.mkdir(parents=True, exist_ok=True)

                # 6. Write final page to disk
                with open(out_path, "w", encoding="utf-8") as f_out:
                    f_out.write(final_html)

                # 7. Update file dependency hash in DAG cache
                self.staleness_tracker.update_cache_for_file(
                    doc_path, getattr(ast, "included_files", []), node_types=page_node_types
                )
                compiled_files.append(out_path)

                # Progress logging
                if not getattr(self.config, "quiet", False):
                    try:
                        rel_doc = doc_path.relative_to(Path.cwd())
                    except ValueError:
                        rel_doc = doc_path.relative_to(self.content_dir) if self.content_dir in doc_path.parents else doc_path
                    try:
                        rel_out = out_path.relative_to(Path.cwd())
                    except ValueError:
                        rel_out = out_path.relative_to(output_dir) if output_dir in out_path.parents else out_path

                    click.echo(f"  [COMPILE] {rel_doc} -> {rel_out}")
            except Exception as e:
                error_info = Diagnostic.from_exception(e, file=str(doc_path))
                self.diagnostics.append(error_info)
                logging.error(f"Failed to build file {doc_path}: {e}")
                if getattr(self.config, "strict", False):
                    raise e

        return compiled_files

    def check(self, files: list[Path] | None = None) -> list[Diagnostic]:
        """Perform syntax parsing and semantic graph resolution diagnostics.

        Parses document ASTs and resolves ASGs to capture AsciiDoc syntax errors,
        malformed block structures, and semantic resolver warnings (such as unresolved
        cross-references) without compiling HTML or writing output files.

        [parameters]
        `files` (list[Path] | None, optional):: Optional explicit list of document files to check.
            If None, checks all non-partial `.adoc` documents in `content_dir`.

        [returns]
        `list[Diagnostic]`:: Collected diagnostic entries (errors and warnings).

        === Examples

        [source,python]
        ----
        >>> from golem.config import GolemConfig
        >>> from golem.engine import BuildEngine
        >>> from pathlib import Path
        >>> config = GolemConfig(content_dir="content", output_dir="dist")
        >>> engine = BuildEngine(config)
        >>> diagnostics = engine.check()
        >>> isinstance(diagnostics, list)
        True
        ----
        """
        self.diagnostics = []
        diagnostics: list[Diagnostic] = []

        if files is None:
            all_docs = (
                [f for f in sorted(self.content_dir.glob("**/*.adoc")) if not is_partial(f, self.content_dir)]
                if self.content_dir.exists()
                else []
            )
        else:
            all_docs = files

        for doc_path in all_docs:
            try:
                with open(doc_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as e:
                diag = Diagnostic.from_exception(e, file=str(doc_path))
                diagnostics.append(diag)
                continue

            # Trigger pre-parse hooks sequentially
            if hasattr(self, "pm") and self.pm:
                for impl in self.pm.hook.on_pre_parse.get_hookimpls():
                    try:
                        result = impl.function(raw_content=content)
                        if isinstance(result, str):
                            content = result
                    except Exception as e:
                        logging.warning(
                            "[Plugin] %s raised an exception in on_pre_parse for %s: %s",
                            impl.plugin_name,
                            doc_path.name,
                            e,
                        )

            # 1. Parse using asciidoctrine
            try:
                ast: Document = asciidoctrine.parse_to_ast(content, base_dir=str(doc_path.parent))
            except Exception as e:
                diag = Diagnostic.from_exception(e, file=str(doc_path))
                diagnostics.append(diag)
                continue

            # Trigger AST hooks sequentially
            if hasattr(self, "pm") and self.pm:
                for impl in self.pm.hook.on_ast_created.get_hookimpls():
                    try:
                        result = impl.function(ast=ast)
                        if isinstance(result, Document):
                            ast = result
                    except Exception as e:
                        logging.warning(
                            "[Plugin] %s raised an exception in on_ast_created for %s: %s",
                            impl.plugin_name,
                            doc_path.name,
                            e,
                        )

            # 2. Resolve AST to ASG
            try:
                resolver = ASGResolver(ast)
                asg: Node = resolver.resolve_to_ast(ast)
                if hasattr(resolver, "warnings") and resolver.warnings:
                    for warn in resolver.warnings:
                        warn_diag = Diagnostic.from_resolver_warning(warn, file=str(doc_path), content=content)
                        diagnostics.append(warn_diag)
            except Exception as e:
                diag = Diagnostic.from_exception(e, file=str(doc_path))
                diagnostics.append(diag)
                continue

            # Trigger ASG hooks sequentially
            if hasattr(self, "pm") and self.pm:
                for impl in self.pm.hook.on_asg_created.get_hookimpls():
                    try:
                        result = _invoke_doc_hook(impl, "asg", asg, doc_path)
                        if isinstance(result, Node):
                            asg = result
                    except Exception as e:
                        logging.warning(
                            "[Plugin] %s raised an exception in on_asg_created for %s: %s",
                            impl.plugin_name,
                            doc_path.name,
                            e,
                        )

        self.diagnostics = diagnostics
        return diagnostics


GolemEngine = BuildEngine
