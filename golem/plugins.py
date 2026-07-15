import os
import sys
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

def get_plugin_manager(plugins_dir: Path = None) -> pluggy.PluginManager:
    pm = pluggy.PluginManager(HOOK_NAMESPACE)
    pm.hookimpl = hookimpl
    pm.add_hookspecs(GolemSpecs)
    
    # 1. Entry point discovery
    pm.load_setuptools_entrypoints(HOOK_NAMESPACE)
    
    # 2. Local plugins folder discovery
    if plugins_dir and plugins_dir.exists() and plugins_dir.is_dir():
        sys.path.insert(0, str(plugins_dir.resolve()))
        for file in plugins_dir.glob("*.py"):
            if file.name == "__init__.py":
                continue
            module_name = file.stem
            spec = importlib.util.spec_from_file_location(module_name, file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                pm.register(module)
    return pm
