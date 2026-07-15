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
