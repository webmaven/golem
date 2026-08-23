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
    @hookspec
    def on_pre_parse(self, raw_content: str) -> str:
        """Executed before the source is parsed."""
        return raw_content

    @hookspec
    def on_ast_created(self, ast: os.PathLike[Any] | Any) -> os.PathLike[Any] | Any:
        """Executed after AST is generated from Lark parsing."""
        return ast

    @hookspec
    def on_asg_created(self, asg: dict[str, Any]) -> dict[str, Any]:
        """Executed after semantic resolver executes."""
        return asg

    @hookspec
    def on_post_render(self, html_content: str) -> str:
        """Executed after Chameleon layout compilation completes."""
        return html_content

    @hookspec
    def golem_add_subcommands(self, cli: click.Group) -> None:
        """Executed during CLI startup to register subcommands with click."""
        pass


def get_plugin_manager(config: GolemConfig | None = None, plugins_dir: Path | None = None) -> pluggy.PluginManager:
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
