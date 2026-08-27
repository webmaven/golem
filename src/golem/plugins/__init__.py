"""
Golem plugin system — hook specifications and plugin manager factory.

Architecture
------------
Golem uses `Pluggy <https://pluggy.readthedocs.io/>`_ for its plugin
system.  All hook specifications live in :class:`GolemSpecs`; the
``@hookspec`` marker registers them under the ``"golem"`` project name.
Plugin implementations must use the matching ``@hookimpl`` marker
(re-exported from this module) and be registered with
:func:`get_plugin_manager`.

Hook execution order
--------------------
Hooks are called in the order plugins were registered.  The four core
document-processing hooks fire in this pipeline sequence for every
source file:

1. :meth:`GolemSpecs.on_pre_parse` — raw AsciiDoc source string
   manipulation (e.g. front-matter injection, include preprocessing).
2. :meth:`GolemSpecs.on_ast_created` — post-parse Lark AST
   transformation (structural rewrites before semantic resolution).
3. :meth:`GolemSpecs.on_asg_created` — post-resolution ASG dict
   manipulation (metadata enrichment, cross-reference injection).
4. :meth:`GolemSpecs.on_post_render` — post-render HTML string
   manipulation (minification, post-processing passes).

Supplementary hooks:

- :meth:`GolemSpecs.golem_add_subcommands` — called once at CLI startup
  so plugins can register additional Click subcommands.
- :meth:`GolemSpecs.golem_mark_stale` — called during incremental build
  dependency resolution so plugins can declare additional stale pages.

Plugin discovery (in priority order)
-------------------------------------
:func:`get_plugin_manager` discovers plugins via three mechanisms:

1. **Entry points** — packages that declare a ``golem.plugins``
   entry-point group are loaded automatically.
2. **Config plugins list** — fully-qualified module names listed in
   :attr:`~golem.config.GolemConfig.plugins` are imported and
   registered.
3. **Local plugins directory** — every ``*.py`` file in
   :attr:`~golem.config.GolemConfig.plugins_dir` (default:
   ``plugins/``) is loaded as a module and registered if it implements
   at least one ``@hookimpl``.

Example plugin skeleton
-----------------------

.. code-block:: python

    from golem.plugins import hookimpl

    @hookimpl
    def on_pre_parse(raw_content: str) -> str:
        # Insert a custom front-matter attribute before parsing
        return ":custom-attr: injected\\n" + raw_content

    @hookimpl
    def on_post_render(html_content: str) -> str:
        return html_content.replace("</body>", "<p>Built by Golem</p></body>")
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
    """Pluggy hook specifications for the Golem plugin system.

    Every method decorated with ``@hookspec`` defines a hook that plugins
    may implement using ``@hookimpl``.  The return value of each hook is
    the value returned by the *last* registered implementation (Pluggy's
    default ``firstresult=False`` behaviour collects all return values;
    Golem passes only the final non-``None`` value downstream).
    """

    @hookspec
    def on_pre_parse(self, raw_content: str) -> str:
        """Transform raw AsciiDoc source text before parsing begins.

        Called once per source file with the complete UTF-8 text of the
        ``.adoc`` file.  Plugins may inject attributes, substitute
        shorthand syntax, or strip proprietary front-matter before the
        string is handed to ``asciidoctrine``.

        === Arguments

        - ``raw_content``:: Complete source text of the ``.adoc`` file.

        === Returns

        Modified source text.  Returning the input unchanged is always
        valid; returning ``None`` or an empty string will produce an
        empty document.
        """
        return raw_content

    @hookspec
    def on_ast_created(self, ast: os.PathLike[Any] | Any) -> os.PathLike[Any] | Any:
        """Transform the parsed Lark AST before semantic resolution.

        Called after ``asciidoctrine`` has produced the raw parse tree
        but before the ``ASGResolver`` walks it.  Use this hook for
        structural tree rewrites that are easier to express at the AST
        level than at the ASG level.

        === Arguments

        - ``ast``:: Lark ``Tree`` object or path-like object as returned
          by ``asciidoctrine.parse()``.

        === Returns

        Modified (or replacement) AST.  Must be compatible with the
        ``ASGResolver`` input contract.
        """
        return ast

    @hookspec
    def on_asg_created(self, asg: dict[str, Any]) -> dict[str, Any]:
        """Transform the resolved ASG dictionary before rendering.

        Called after the ``ASGResolver`` has produced a fully-resolved
        Abstract Semantic Graph from the Lark AST.  The ASG is a nested
        Python ``dict`` whose root node has ``"name": "document"`` and a
        ``"blocks"`` list.

        Use this hook to inject computed metadata (e.g. API cross-
        references, breadcrumb information, or dynamic admonitions) that
        cannot be expressed as static AsciiDoc source.

        === Arguments

        - ``asg``:: Resolved document ASG as a nested ``dict``.

        === Returns

        Modified (or replacement) ASG ``dict``.  Must conform to the
        ``asciidoctype.AsciiDoctypeRenderer`` input contract.
        """
        return asg

    @hookspec
    def on_post_render(self, html_content: str) -> str:
        """Transform the rendered HTML string after Chameleon layout compilation.

        Called with the final rendered HTML page string, including the
        full Chameleon ``skeleton.pt`` layout wrapper.  Use this hook
        for post-processing passes such as HTML minification, analytics
        snippet injection, or link rewriting.

        === Arguments

        - ``html_content``:: Complete rendered HTML page string.

        === Returns

        Modified HTML string.  Returning the input unchanged is always
        valid.
        """
        return html_content

    @hookspec
    def golem_add_subcommands(self, cli: click.Group) -> None:
        """Register additional Click subcommands with the Golem CLI.

        Called once during ``golem`` CLI startup after all built-in
        subcommands have been attached.  Plugins can attach their own
        :class:`click.Command` or :class:`click.Group` objects here.

        === Arguments

        - ``cli``:: The root :class:`click.Group` (``golem``).  Call
          ``cli.add_command(my_cmd)`` to register a subcommand.

        === Returns

        ``None``.  Return values are ignored.

        === Example

        .. code-block:: python

            import click
            from golem.plugins import hookimpl

            @hookimpl
            def golem_add_subcommands(cli: click.Group) -> None:
                @cli.command("export-pdf")
                @click.argument("output")
                def export_pdf(output: str) -> None:
                    \"\"\"Export the built site to a single PDF.\"\"\"
                    ...
        """
        pass

    @hookspec
    def golem_mark_stale(
        self,
        changed_files: list[Path],
        cache_metadata: dict[str, dict[str, Any]],
    ) -> list[Path] | None:
        """Declare additional pages that must be rebuilt due to changed dependencies.

        Called during the incremental build dependency resolution phase,
        after the engine has identified which source ``.adoc`` files have
        changed on disk.  Plugins that maintain their own dependency
        graph (e.g. the ``apidoc`` plugin tracking Python source changes)
        can inspect *changed_files* and return additional ``.adoc`` paths
        that transitively depend on them.

        === Arguments

        - ``changed_files``:: List of :class:`~pathlib.Path` objects for
          ``.adoc`` files (and other tracked assets) that have changed
          since the last build.
        - ``cache_metadata``:: Snapshot of the current build cache — a
          ``dict`` mapping absolute file path strings to their per-file
          metadata dicts (title, hash, node types, etc.).  Read-only;
          mutations are ignored.

        === Returns

        List of :class:`~pathlib.Path` objects for additional ``.adoc``
        pages that should be considered stale and rebuilt, or ``None`` /
        ``[]`` if no additional pages are affected.
        """
        return []


def get_plugin_manager(config: GolemConfig | None = None, plugins_dir: Path | None = None) -> pluggy.PluginManager:
    """Build and return a configured :class:`~pluggy.PluginManager` for Golem.

    Registers :class:`GolemSpecs`, then discovers plugins via three
    mechanisms in priority order (see module docstring for details):
    entry points → config plugin list → local plugins directory.

    Loading failures (import errors, broken modules) are logged as
    warnings and skipped rather than aborting the build, so a broken
    optional plugin does not prevent the core site from being built.

    === Arguments

    - ``config``:: Optional :class:`~golem.config.GolemConfig` instance.
      When provided, :attr:`~golem.config.GolemConfig.plugins` (module
      name list) and :attr:`~golem.config.GolemConfig.plugins_dir`
      (local directory) are used for discovery.
    - ``plugins_dir``:: Explicit override for the local plugins directory.
      Takes precedence over ``config.plugins_dir`` when supplied.

    === Returns

    A :class:`~pluggy.PluginManager` with all discovered plugins
    registered and the ``golem`` hook specifications loaded.
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
