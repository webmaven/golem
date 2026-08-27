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
import importlib.util
import logging
import os
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
    def on_ast_created(self, ast: os.PathLike[Any] | Any) -> os.PathLike[Any] | Any:
        """Intercept and transform the parsed Abstract Syntax Tree (AST) before semantic resolution.

        Executed after Lark parses raw AsciiDoc text into an initial syntax tree.
        Plugins can mutate AST nodes, inject custom syntax constructs, or validate tree
        structure before the AST is passed to the semantic ASG resolver.

        [parameters]
        `ast` (os.PathLike[Any] | Any):: Parsed Abstract Syntax Tree root node produced by the Lark parser.

        [returns]
        `os.PathLike[Any] | Any`:: Mutated or substituted AST structure for semantic resolution.

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
    def on_asg_created(self, asg: dict[str, Any]) -> dict[str, Any]:
        """Intercept and transform the Abstract Semantic Graph (ASG) dictionary after resolution.

        Executed after the semantic resolver converts the AST into a structured ASG dictionary.
        Plugins can enrich document metadata, modify section and block hierarchies, inject
        synthetic blocks, or alter resolved attributes before HTML rendering.

        [parameters]
        `asg` (dict[str, Any]):: Semantic graph representation of the document containing resolved blocks, metadata, and attributes.

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


def get_plugin_manager(config: GolemConfig | None = None, plugins_dir: Path | None = None) -> pluggy.PluginManager:
    """Initialize and configure a Pluggy PluginManager with discovered Golem plugins.

    Creates a `pluggy.PluginManager` bound to the `"golem"` namespace, registers
    `GolemSpecs` hook specifications, and discovers plugins across three sequential tiers:
    1. **Setuptools Entrypoints**: Discovers distributions registered under `"golem.plugins"` and `"golem"`.
    2. **Configured Plugins**: Imports and registers module or package paths declared in `config.plugins`.
    3. **Local Plugins Folder**: Scans the designated plugins directory (`plugins_dir`, `config.plugins_dir`, or `"plugins"` default), dynamically loads standalone `*.py` modules (excluding `__init__.py`), and ensures the directory is present on `sys.path`.

    [parameters]
    `config` (GolemConfig | None, optional):: Site configuration object providing plugin lists and directory settings. Defaults to `None`.
    `plugins_dir` (Path | None, optional):: Explicit filesystem path to local plugins directory. Overrides `config.plugins_dir`. Defaults to `None`.

    [returns]
    `pluggy.PluginManager`:: Initialized and configured plugin manager instance with all discovered hooks registered.

    [source,python]
    ----
    from pathlib import Path
    from golem.config import GolemConfig
    from golem.plugins import get_plugin_manager

    config = GolemConfig(plugins=["my_package.plugin"])
    pm = get_plugin_manager(config=config, plugins_dir=Path("plugins"))
    results = pm.hook.on_pre_parse(raw_content="= Page Title")
    ----
    """
    pm = pluggy.PluginManager(HOOK_NAMESPACE)
    pm.hookimpl = hookimpl  # type: ignore[attr-defined]
    pm.add_hookspecs(GolemSpecs)

    # Determine target plugins directory
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

    # 1. Entry point discovery
    pm.load_setuptools_entrypoints("golem.plugins")
    pm.load_setuptools_entrypoints(HOOK_NAMESPACE)

    # 2. Configured plugins loading (full package strings or module names)
    if config is not None and getattr(config, "plugins", None):
        for mod_name in config.plugins:
            try:
                mod = importlib.import_module(mod_name)
                if not pm.is_registered(mod):
                    pm.register(mod)
            except Exception as e:
                logging.warning("Failed to load plugin %s: %s", mod_name, e)

    # 3. Local plugins folder discovery
    if target_plugins_dir and target_plugins_dir.exists() and target_plugins_dir.is_dir():
        for file in target_plugins_dir.glob("*.py"):
            if file.name == "__init__.py":
                continue
            module_name = file.stem
            try:
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    if not pm.is_registered(module):
                        pm.register(module)
            except Exception as e:
                logging.warning("Failed to load local plugin %s: %s", file, e)
    return pm
