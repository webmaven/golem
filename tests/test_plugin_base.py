from typing import Any

from golem.config import GolemConfig
from golem.plugins import GolemPlugin, __all__ as plugins_all


class SamplePlugin(GolemPlugin):
    name = "golem.plugins.sample"

    def __init__(self, key: str = "default", count: int = 0, **extra: Any) -> None:
        super().__init__(key=key, count=count, **extra)
        self.key = key
        self.count = count


def test_golem_plugin_exported_in_all():
    assert "GolemPlugin" in plugins_all


def test_golem_plugin_init_defaults():
    plugin = GolemPlugin()
    assert plugin.config == {}


def test_golem_plugin_init_kwargs():
    plugin = GolemPlugin(foo="bar", num=123)
    assert plugin.config == {"foo": "bar", "num": 123}


def test_golem_plugin_from_config_none():
    plugin = SamplePlugin.from_config(None)
    assert isinstance(plugin, SamplePlugin)
    assert plugin.key == "default"
    assert plugin.count == 0


def test_golem_plugin_from_config_dict_full_name():
    config = {"golem.plugins.sample": {"key": "custom", "count": 5}}
    plugin = SamplePlugin.from_config(config)
    assert plugin.key == "custom"
    assert plugin.count == 5


def test_golem_plugin_from_config_dict_short_name():
    config = {"sample": {"key": "from_short", "count": 10}}
    plugin = SamplePlugin.from_config(config)
    assert plugin.key == "from_short"
    assert plugin.count == 10


def test_golem_plugin_from_config_dict_with_plugin_configs_key():
    config = {"plugin_configs": {"sample": {"key": "from_nested", "count": 20}}}
    plugin = SamplePlugin.from_config(config)
    assert plugin.key == "from_nested"
    assert plugin.count == 20


def test_golem_plugin_from_config_golem_config_full_name():
    config = GolemConfig(plugin_configs={"golem.plugins.sample": {"key": "golem_cfg", "count": 42}})
    plugin = SamplePlugin.from_config(config)
    assert plugin.key == "golem_cfg"
    assert plugin.count == 42


def test_golem_plugin_from_config_golem_config_short_name():
    config = GolemConfig(plugin_configs={"sample": {"key": "golem_cfg_short", "count": 99}})
    plugin = SamplePlugin.from_config(config)
    assert plugin.key == "golem_cfg_short"
    assert plugin.count == 99


def test_golem_plugin_from_config_empty_config():
    config = GolemConfig()
    plugin = SamplePlugin.from_config(config)
    assert plugin.key == "default"
    assert plugin.count == 0
