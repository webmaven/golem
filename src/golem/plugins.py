import os
import sys
import logging
import importlib.util
import pluggy
from pathlib import Path

HOOK_NAMESPACE = "golem"

hookspec = pluggy.HookspecMarker(HOOK_NAMESPACE)
hookimpl = pluggy.HookimplMarker(HOOK_NAMESPACE)

class GolemSpecs:
    @hookspec
    def on_pre_parse(self, raw_content: str) -> str:
        """Executed before the source is parsed."""
        return raw_content

    @hookspec
    def on_ast_created(self, ast: os.PathLike) -> os.PathLike:
        """Executed after AST is generated from Lark parsing."""
        return ast

    @hookspec
    def on_asg_created(self, asg: dict) -> dict:
        """Executed after semantic resolver executes."""
        return asg

    @hookspec
    def on_post_render(self, html_content: str) -> str:
        """Executed after Chameleon layout compilation completes."""
        return html_content

def get_plugin_manager(plugins_dir: Path | None = None) -> pluggy.PluginManager:
    pm = pluggy.PluginManager(HOOK_NAMESPACE)
    pm.hookimpl = hookimpl  # type: ignore[attr-defined]
    pm.add_hookspecs(GolemSpecs)
    
    # 1. Entry point discovery
    pm.load_setuptools_entrypoints(HOOK_NAMESPACE)
    
    # 2. Local plugins folder discovery
    if plugins_dir and plugins_dir.exists() and plugins_dir.is_dir():
        resolved_path = str(plugins_dir.resolve())
        if resolved_path not in sys.path:
            sys.path.insert(0, resolved_path)
        for file in plugins_dir.glob("*.py"):
            if file.name == "__init__.py":
                continue
            module_name = file.stem
            try:
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    pm.register(module)
            except Exception as e:
                logging.warning("Failed to load local plugin %s: %s", file, e)
    return pm
