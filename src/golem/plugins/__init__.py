"""Provide the Pluggy-based plugin architecture and lifecycle hook specifications for Golem.

== Architecture Overview

Golem leverages `pluggy` to provide a modular extension ecosystem:
1. `HOOK_NAMESPACE`: Hook specifications and implementations are scoped to the `"golem"` namespace.
2. `hookspec`: Decorator marking hook specification contracts in `GolemSpecs`.
3. `hookimpl`: Decorator marking plugin hook implementations in user-defined modules or classes.
4. `PluginManager`: Central registry managing hook discovery, registration, and dispatch.

== Hook Execution Order & Lifecycle

During site compilation and CLI initialization, hooks execute across discrete pipeline stages:

1. CLI Initialization (`golem_add_subcommands`)::
   Executed during Click CLI bootstrap. Registered plugins attach custom subcommands to the root CLI group before command parsing.
2. Incremental Cache Resolution (`golem_mark_stale`)::
   Executed during dependency graph resolution before page processing. Plugins inspect modified files and cache metadata to mark additional dependent pages as stale.
3. Pre-Parse Transformation (`on_pre_parse`)::
   Executed sequentially per document. Plugins receive raw AsciiDoc source text and return modified content prior to Lark syntax parsing (e.g. macro preprocessing).
4. AST Transformation (`on_ast_created`)::
   Executed after Lark parses AsciiDoc source into an Abstract Syntax Tree (AST). Plugins mutate or wrap syntax nodes prior to semantic resolution.
5. ASG Transformation (`on_asg_created`)::
   Executed after the semantic resolver transforms the AST into an Abstract Semantic Graph (ASG) dictionary. Plugins mutate semantic nodes, table metadata, or document attributes.
6. Layout Compilation & Post-Render (`on_post_render`)::
   Executed after Chameleon template layout rendering. Plugins receive the compiled HTML page string and return modified HTML before it is written to disk.

== Plugin Discovery Order

When initializing via `get_plugin_manager()`, plugins are discovered and registered in the following order:

1. Setuptools Entrypoints::
   Discovers installed distributions advertising the `"golem.plugins"` or `"golem"` entry point groups.
2. Configured Modules::
   Loads and registers Python modules or package paths specified in the `plugins` list of `GolemConfig`.
3. Local Plugins Directory::
   Scans the designated plugins directory (e.g. `plugins/`), dynamically imports standalone `*.py` files (excluding `__init__.py`), and adds the directory to `sys.path`.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
import pluggy

if TYPE_CHECKING:
    from golem.config import GolemConfig

HOOK_NAMESPACE = "golem"

hookspec = pluggy.HookspecMarker(HOOK_NAMESPACE)
hookimpl = pluggy.HookimplMarker(HOOK_NAMESPACE)


class GolemSpecs:
    """Define Pluggy hook specifications for Golem extension points and build pipeline hooks.

    Plugins implement these hook specifications by decorating functions or methods with
    `@hookimpl` from `golem.plugins`. Hook implementations can be packaged as standalone
    classes or module-level functions.

    [source,python]
    ----
    from golem.plugins import hookimpl

    class CustomPlugin:
        @hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content.replace(":custom_tag:", "Expanded Tag")
    ----

    Plugin Activation::
        Plugins are activated exclusively by listing them in `config.plugins`, regardless of
        how they are discovered (installed entry points, local `plugins/` directory files, or
        importlib module paths). Presence alone — being installed or placed in `plugins/` — does
        not activate a plugin. This ensures reproducible builds and explicit opt-in.

    Hook Execution Order::
        Transform hooks (`on_pre_parse`, `on_ast_created`, `on_asg_created`, `on_post_render`)
        execute in the order plugins appear in `config.plugins`. The first listed plugin runs
        first; its output becomes the input to the second, and so on. A `logging.WARNING` is
        emitted at build time when multiple plugins modify the same value in a single hook,
        since the final result is then dependent on list order.

    Plugin Authoring Best Practice — Additive Transforms::
        To minimize order-sensitivity, implement transform hooks as additive and commutative
        operations where possible:

        * Good (additive): Replacing a specific macro token that no other plugin touches,
          appending a metadata key that doesn't already exist, injecting a script tag before
          `</body>`.
        * Risky (order-sensitive): Reordering document sections, overwriting a shared metadata
          key, making assumptions about what a prior plugin has or has not already done.

        Plugins that are inherently order-sensitive should document that dependency explicitly.
    """

    @hookspec
    def on_pre_parse(self, raw_content: str) -> str:
        """Intercept and transform raw AsciiDoc source content prior to syntax parsing.

        Executed sequentially across registered plugins during site compilation before
        Lark parsing is performed. Each plugin receives the output of the preceding plugin,
        enabling source text macro expansion, dynamic token replacement, and variable injection.

        [parameters]
        `raw_content` (str):: Raw AsciiDoc source text read from the document file.

        [returns]
        `str`:: Transformed AsciiDoc source text passed to downstream parsers.

        [source,python]
        ----
        from golem.plugins import hookimpl

        @hookimpl
        def on_pre_parse(raw_content: str) -> str:
            return raw_content.replace("{current_year}", "2026")
        ----
        """
        return raw_content

    @hookspec
    def on_ast_created(self, ast: Any) -> Any:
        """Intercept and transform the parsed Abstract Syntax Tree (AST) before semantic resolution.

        Executed after Lark parses raw AsciiDoc text into an initial syntax tree.
        Plugins can mutate AST nodes, inject custom syntax constructs, or validate tree
        structure before the AST is passed to the semantic ASG resolver.

        [parameters]
        `ast` (Any):: Parsed Abstract Syntax Tree root node produced by the Lark parser.

        [returns]
        `Any`:: Mutated or substituted AST structure for semantic resolution.

        [source,python]
        ----
        from typing import Any
        from golem.plugins import hookimpl

        @hookimpl
        def on_ast_created(ast: Any) -> Any:
            # Inspect or mutate AST tree nodes
            return ast
        ----
        """
        return ast

    @hookspec
    def on_asg_created(self, asg: dict[str, Any], doc_path: Path | None = None) -> dict[str, Any]:
        """Intercept and transform the Abstract Semantic Graph (ASG) dictionary after resolution.

        Executed after the semantic resolver converts the AST into a structured ASG dictionary.
        Plugins can enrich document metadata, modify section and block hierarchies, inject
        synthetic blocks, or alter resolved attributes before HTML rendering.

        [parameters]
        `asg` (dict[str, Any]):: Semantic graph representation of the document containing resolved blocks, metadata, and attributes.
        `doc_path` (Path | None, optional):: Optional Path to the document being compiled.

        [returns]
        `dict[str, Any]`:: Enriched or modified ASG dictionary passed to the body renderer.

        [source,python]
        ----
        from typing import Any
        from golem.plugins import hookimpl

        @hookimpl
        def on_asg_created(asg: dict[str, Any]) -> dict[str, Any]:
            asg["injected_metadata"] = {"status": "reviewed"}
            return asg
        ----
        """
        return asg

    @hookspec
    def on_post_render(self, html_content: str) -> str:
        """Intercept and transform compiled HTML content prior to writing to disk.

        Executed after ASG body rendering and Chameleon layout template compilation
        have generated the complete HTML document string. Plugins can perform post-processing
        such as HTML minification, injecting tracking scripts, syntax highlighting adjustments,
        or rewriting asset URLs.

        [parameters]
        `html_content` (str):: Fully compiled HTML document string including layout shell and rendered body.

        [returns]
        `str`:: Transformed HTML document string to write to output destination.

        [source,python]
        ----
        from golem.plugins import hookimpl

        @hookimpl
        def on_post_render(html_content: str) -> str:
            return html_content.replace("</body>", "<!-- rendered by golem --></body>")
        ----
        """
        return html_content

    @hookspec
    def golem_add_subcommands(self, cli: click.Group) -> None:
        """Register custom Click CLI subcommands during Golem command line initialization.

        Executed during CLI startup when Click initializes command groups. Plugins
        can attach custom subcommands, tools, generators, or deployment tasks to the
        main `golem` command group.

        [parameters]
        `cli` (click.Group):: Root or parent Click command group to which new subcommands are attached.

        [returns]
        `None`:: Hook returns no value.

        [source,python]
        ----
        import click
        from golem.plugins import hookimpl

        @hookimpl
        def golem_add_subcommands(cli: click.Group) -> None:
            @cli.command("greet")
            @click.option("--name", default="World")
            def greet_command(name: str) -> None:
                click.echo(f"Hello, {name}!")
        ----
        """
        pass

    @hookspec
    def golem_mark_stale(
        self,
        changed_files: list[Path],
        cache_metadata: dict[str, dict[str, Any]],
    ) -> list[Path] | None:
        """Register additional stale source files for recompilation during incremental builds.

        Executed during dependency graph resolution. Plugins analyze directly modified or
        deleted files alongside cached dependency metadata to identify indirect dependencies
        (such as shared data files, API stubs, taxonomy pages, or global indexes) that must
        be marked stale and recompiled.

        [parameters]
        `changed_files` (list[Path]):: List of file paths directly modified or deleted in the current build cycle.
        `cache_metadata` (dict[str, dict[str, Any]]):: Cached build metadata mapping file paths to node types, included files, and content hashes.

        [returns]
        `list[Path] | None`:: List of additional file paths to mark as stale for recompilation, or `None` if no additional files require rebuilding.

        [source,python]
        ----
        from pathlib import Path
        from typing import Any
        from golem.plugins import hookimpl

        @hookimpl
        def golem_mark_stale(
            changed_files: list[Path],
            cache_metadata: dict[str, dict[str, Any]],
        ) -> list[Path] | None:
            # Mark index page stale if any data file changed
            if any(f.suffix == ".json" for f in changed_files):
                return [Path("content/index.adoc")]
            return None
        ----
        """
        return []


_CACHED_ENTRY_POINTS: dict[str, tuple[str, Any]] | None = None


def _get_entry_point_plugins(clear_cache: bool = False) -> dict[str, tuple[str, Any]]:
    """Discover and cache entry points from installed distributions."""
    global _CACHED_ENTRY_POINTS
    if _CACHED_ENTRY_POINTS is None or clear_cache:
        eps: dict[str, tuple[str, Any]] = {}
        for group in ("golem.plugins", HOOK_NAMESPACE):
            for ep in importlib.metadata.entry_points(group=group):
                ep_name = getattr(ep, "name", str(ep))
                ep_value = getattr(ep, "value", "")
                if ep_name not in eps:
                    eps[ep_name] = ("entrypoint", ep)
                if ep_value and ep_value not in eps:
                    eps[ep_value] = ("entrypoint", ep)
        _CACHED_ENTRY_POINTS = eps
    return _CACHED_ENTRY_POINTS


def get_plugin_manager(
    config: GolemConfig | None = None,
    plugins_dir: Path | None = None,
) -> pluggy.PluginManager:
    """Initialize and configure a Pluggy PluginManager with plugins from config.plugins.

    Uses a two-pass discovery → registration architecture.

    1. Discovery pass: Scans entry points, the local plugins directory, and importlib-importable
       module paths, building a lookup map of available plugins. Nothing is registered here.
    2. Registration pass: Iterates ``config.plugins`` in list order, looks up each entry, and
       registers it. ``config.plugins`` is the sole authority on enablement and execution order.

    [parameters]
    `config` (GolemConfig | None, optional):: Site configuration providing ``plugins``
        list and directory settings.
    `plugins_dir` (Path | None, optional):: Explicit plugins directory override.

    [returns]
    `pluggy.PluginManager`:: Configured plugin manager with only listed plugins registered.
    """
    pm = pluggy.PluginManager(HOOK_NAMESPACE)
    pm.hookimpl = hookimpl  # type: ignore[attr-defined]
    pm.add_hookspecs(GolemSpecs)

    # Resolve local plugins directory
    target_plugins_dir: Path | None = None
    if plugins_dir is not None:
        target_plugins_dir = plugins_dir
    elif config is not None and getattr(config, "plugins_dir", None):
        target_plugins_dir = Path(config.plugins_dir)
    else:
        default_dir = Path("plugins")
        if default_dir.exists() and default_dir.is_dir():
            target_plugins_dir = default_dir

    if target_plugins_dir and target_plugins_dir.exists() and target_plugins_dir.is_dir():
        resolved_path = str(target_plugins_dir.resolve())
        if resolved_path not in sys.path:
            sys.path.insert(0, resolved_path)

    # --- PASS 1: DISCOVERY ---
    # Build a name → (kind, source) lookup. Nothing is registered here.
    available: dict[str, tuple[str, Any]] = dict(_get_entry_point_plugins())

    if target_plugins_dir and target_plugins_dir.exists() and target_plugins_dir.is_dir():
        for file in target_plugins_dir.glob("*.py"):
            if file.name == "__init__.py":
                continue
            stem = file.stem
            rel_path = f"{target_plugins_dir.as_posix()}/{file.name}"
            for key in (stem, file.name, f"{target_plugins_dir.name}.{stem}", rel_path):
                if key not in available:
                    available[key] = ("local_file", file)

    # --- PASS 2: REGISTRATION ---
    # config.plugins is the sole authority: list order = execution order.
    configured = list(config.plugins) if (config is not None and config.plugins) else []

    for plugin_name in configured:
        try:
            if plugin_name in available:
                kind, source = available[plugin_name]
                if kind == "entrypoint":
                    plugin = source.load()
                    if not pm.is_registered(plugin):
                        pm.register(plugin, name=plugin_name)
                elif kind == "local_file":
                    spec = importlib.util.spec_from_file_location(source.stem, source)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[source.stem] = module
                        spec.loader.exec_module(module)
                        if not pm.is_registered(module):
                            pm.register(module, name=plugin_name)
            else:
                # Fall back to importlib for fully-qualified module paths
                mod = importlib.import_module(plugin_name)
                if not pm.is_registered(mod):
                    pm.register(mod)
        except Exception as e:
            logging.warning("Failed to load plugin %s: %s", plugin_name, e)

    return pm
