import pytest
from golem.plugins import get_plugin_manager

def test_plugin_hook_trigger():
    pm = get_plugin_manager()
    # Define a mock plugin
    class MockPlugin:
        @get_plugin_manager().hookimpl
        def on_pre_parse(self, raw_content: str) -> str:
            return raw_content.replace("draft", "final")
            
    pm.register(MockPlugin())
    res = pm.hook.on_pre_parse(raw_content="This is a draft version.")
    # Pluggy returns results in a list
    assert "This is a final version." in res

def test_local_plugin_discovery(tmp_path):
    # Create a dynamic plugin file in the temporary directory
    plugin_content = """
from golem.plugins import hookimpl

@hookimpl
def on_pre_parse(raw_content: str) -> str:
    return f"Dynamic: {raw_content}"
"""
    plugin_file = tmp_path / "my_test_plugin.py"
    plugin_file.write_text(plugin_content, encoding="utf-8")
    
    # Load plugin manager passing the temporary path
    pm = get_plugin_manager(plugins_dir=tmp_path)
    
    # Verify hook can be triggered and the dynamic plugin worked
    res = pm.hook.on_pre_parse(raw_content="hello")
    assert "Dynamic: hello" in res

def test_local_plugin_error_isolation(tmp_path):
    # Create a broken plugin file (has runtime syntax/execution error)
    plugin_content = """
raise ValueError("Plugin failed intentionally during import!")
"""
    plugin_file = tmp_path / "broken_plugin.py"
    plugin_file.write_text(plugin_content, encoding="utf-8")
    
    # Loading plugins should not raise an exception, just skip broken ones
    pm = get_plugin_manager(plugins_dir=tmp_path)
    assert pm is not None

