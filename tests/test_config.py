# tests/test_config.py
import pytest
from pathlib import Path
from golem.config import GolemConfig, load_config, find_default_config_path


def test_config_parsing(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[site]
title = "My Test Docs"
author = "Doc Writer"

[build]
content_dir = "my_content"
output_dir = "my_dist"
""")
    config = load_config(config_file)
    assert config.site_title == "My Test Docs"
    assert config.site_author == "Doc Writer"
    assert config.content_dir == "my_content"
    assert config.output_dir == "my_dist"


def test_load_config_non_existent():
    config = load_config(Path("non_existent_file.toml"))
    assert isinstance(config, GolemConfig)
    assert config.site_title == "Golem Docs"
    assert config.site_author == "Anonymous"
    assert config.content_dir == "content"
    assert config.output_dir == "dist"
    assert config.theme == "default"


def test_config_parsing_partial(tmp_path):
    config_file_empty = tmp_path / "golem_empty.toml"
    config_file_empty.write_text("")
    config = load_config(config_file_empty)
    assert config.site_title == "Golem Docs"
    assert config.site_author == "Anonymous"
    assert config.content_dir == "content"
    assert config.output_dir == "dist"
    assert config.theme == "default"

    config_file_partial = tmp_path / "golem_partial.toml"
    config_file_partial.write_text("""
[site]
title = "Partial Title"
""")
    config_partial = load_config(config_file_partial)
    assert config_partial.site_title == "Partial Title"
    assert config_partial.site_author == "Anonymous"
    assert config_partial.content_dir == "content"
    assert config_partial.output_dir == "dist"
    assert config_partial.theme == "default"


def test_pyproject_toml_nested_parsing(tmp_path):
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text("""
[tool.golem.site]
title = "Library Docs"
author = "Dev Team"

[tool.golem.build]
content_dir = "src_docs"
output_dir = "build_out"
theme = "custom"
""")
    config = load_config(config_file)
    assert config.site_title == "Library Docs"
    assert config.site_author == "Dev Team"
    assert config.content_dir == "src_docs"
    assert config.output_dir == "build_out"
    assert config.theme == "custom"


def test_pyproject_toml_flattened_parsing(tmp_path):
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text("""
[tool.golem]
title = "Flattened Library Docs"
author = "Dev Team Flat"
content_dir = "src_docs_flat"
output_dir = "build_out_flat"
theme = "flat_theme"
""")
    config = load_config(config_file)
    assert config.site_title == "Flattened Library Docs"
    assert config.site_author == "Dev Team Flat"
    assert config.content_dir == "src_docs_flat"
    assert config.output_dir == "build_out_flat"
    assert config.theme == "flat_theme"


def test_find_default_config_path_resolution(tmp_path, monkeypatch):
    # Change current working directory to a isolated temp directory
    monkeypatch.chdir(tmp_path)

    # 1. No files exist -> should return golem.toml
    assert find_default_config_path() == Path("golem.toml")

    # 2. Only pyproject.toml exists but without [tool.golem] -> should return golem.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[tool.poetry]\nname = "test"')
    assert find_default_config_path() == Path("golem.toml")

    # 3. pyproject.toml exists with [tool.golem] -> should return pyproject.toml
    pyproject.write_text('[tool.golem]\ntitle = "Test"')
    assert find_default_config_path() == Path("pyproject.toml")

    # 4. Both exist -> should prefer golem.toml
    golem = tmp_path / "golem.toml"
    golem.write_text("")
    assert find_default_config_path() == Path("golem.toml")


def test_config_overlap_prevention(tmp_path):
    # Overlapping identical content and output directories
    with pytest.raises(ValueError, match="overlap"):
        config_file = tmp_path / "golem.toml"
        config_file.write_text("""
[build]
content_dir = "docs"
output_dir = "docs"
""")
        load_config(config_file)

    # Nested content_dir inside output_dir
    with pytest.raises(ValueError, match="overlap"):
        config_file2 = tmp_path / "golem2.toml"
        config_file2.write_text("""
[build]
content_dir = "dist/content"
output_dir = "dist"
""")
        load_config(config_file2)


def test_config_toml_syntax_error(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[site
title = "Malformed
""")
    with pytest.raises(ValueError, match="Failed to parse configuration file"):
        load_config(config_file)


def test_config_site_url_strict_nav_defaults():
    config = GolemConfig()
    assert config.site_url is None
    assert config.strict is False
    assert config.navigation_nav is None


def test_config_site_url_strict_nav_from_golem_toml(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[site]
title = "My Docs"
url = "https://example.com/docs"
author = "Dev"

[build]
strict = true

[navigation]
nav = ["01-getting-started.adoc", "02-architecture.adoc"]
""")
    config = load_config(config_file)
    assert config.site_title == "My Docs"
    assert config.site_url == "https://example.com/docs"
    assert config.strict is True
    assert config.navigation_nav == ["01-getting-started.adoc", "02-architecture.adoc"]


def test_config_pyproject_toml_site_url_strict_nav(tmp_path):
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text("""
[tool.golem.site]
title = "PyProject Docs"
url = "https://pyproject.org/docs"

[tool.golem.build]
strict = true

[tool.golem.navigation]
nav = [
    { title = "Intro", path = "01-intro.adoc" },
    { title = "Guide", path = "02-guide.adoc" }
]
""")
    config = load_config(config_file)
    assert config.site_title == "PyProject Docs"
    assert config.site_url == "https://pyproject.org/docs"
    assert config.strict is True
    assert config.navigation_nav == ["01-intro.adoc", "02-guide.adoc"]


def test_config_plugins_and_static_defaults():
    config = GolemConfig()
    assert config.plugins == []
    assert config.static_dir == "static"


def test_config_plugins_unspecified_in_file(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[site]
title = "Default Plugins Docs"
""")
    config = load_config(config_file)
    assert config.plugins == []
    assert config.static_dir == "static"


def test_config_plugins_golem_toml_plugins_list(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[plugins]
plugins = ["custom.plugin1", "custom.plugin2"]
""")
    config = load_config(config_file)
    assert config.plugins == ["custom.plugin1", "custom.plugin2"]


def test_config_plugins_golem_toml_enabled_list(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[plugins]
enabled = ["enabled.plugin1", "enabled.plugin2"]
""")
    config = load_config(config_file)
    assert config.plugins == ["enabled.plugin1", "enabled.plugin2"]


def test_config_plugins_golem_toml_toplevel_plugins(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
plugins = ["top.plugin1", "top.plugin2"]
""")
    config = load_config(config_file)
    assert config.plugins == ["top.plugin1", "top.plugin2"]


def test_config_plugins_table_items_with_name(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[plugins]
plugins = [
    { name = "dict.plugin1", enabled = true },
    "string.plugin2"
]
""")
    config = load_config(config_file)
    assert config.plugins == ["dict.plugin1", "string.plugin2"]

    config_file_tables = tmp_path / "golem_tables.toml"
    config_file_tables.write_text("""
[[plugins]]
name = "table.plugin1"

[[plugins]]
name = "table.plugin2"
""")
    config_tables = load_config(config_file_tables)
    assert config_tables.plugins == ["table.plugin1", "table.plugin2"]


def test_config_plugins_empty_list(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[plugins]
plugins = []
""")
    config = load_config(config_file)
    assert config.plugins == []

    config_file_top = tmp_path / "golem_top.toml"
    config_file_top.write_text("""
plugins = []
""")
    config_top = load_config(config_file_top)
    assert config_top.plugins == []


def test_config_plugins_pyproject_toml(tmp_path):
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text("""
[tool.golem.plugins]
plugins = ["golem.plugins.doctest", "golem.plugins.apidoc"]
""")
    config = load_config(config_file)
    assert config.plugins == ["golem.plugins.doctest", "golem.plugins.apidoc"]

    config_file_enabled = tmp_path / "pyproject_enabled.toml"
    config_file_enabled.write_text("""
[tool.golem.plugins]
enabled = ["tool.enabled1"]
""")
    config_enabled = load_config(config_file_enabled)
    assert config_enabled.plugins == ["tool.enabled1"]

    config_file_flat = tmp_path / "pyproject_flat.toml"
    config_file_flat.write_text("""
[tool.golem]
plugins = ["tool.flat1"]
""")
    config_flat = load_config(config_file_flat)
    assert config_flat.plugins == ["tool.flat1"]

    config_file_table = tmp_path / "pyproject_table.toml"
    config_file_table.write_text("""
[[tool.golem.plugins]]
name = "tool.table.plugin"
""")
    config_table = load_config(config_file_table)
    assert config_table.plugins == ["tool.table.plugin"]

    config_file_empty = tmp_path / "pyproject_empty.toml"
    config_file_empty.write_text("""
[tool.golem.plugins]
plugins = []
""")
    config_empty = load_config(config_file_empty)
    assert config_empty.plugins == []


def test_config_static_dir_custom(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[build]
static_dir = "assets"
""")
    config = load_config(config_file)
    assert config.static_dir == "assets"

    config_file_pyproject = tmp_path / "pyproject.toml"
    config_file_pyproject.write_text("""
[tool.golem.build]
static_dir = "my_assets"
""")
    config_pyproject = load_config(config_file_pyproject)
    assert config_pyproject.static_dir == "my_assets"
