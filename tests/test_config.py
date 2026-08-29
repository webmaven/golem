# tests/test_config.py
import pytest
from pathlib import Path
from golem.config import (
    GolemConfig,
    _extract_config_values,
    _resolve_plugins_raw,
    find_default_config_path,
    load_config,
)


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


def test_config_api_defaults():
    config = GolemConfig()
    assert config.api_packages == []
    assert config.api_output_dir == "api"
    assert config.api_docstring_style == "auto"


def test_config_api_golem_toml(tmp_path):
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[site]
title = "API Test Docs"

[api]
packages = ["golem", "mymodule"]
output_dir = "reference/api"
docstring_style = "google"
""")
    config = load_config(config_file)
    assert config.api_packages == ["golem", "mymodule"]
    assert config.api_output_dir == "reference/api"
    assert config.api_docstring_style == "google"


def test_config_api_pyproject_toml(tmp_path):
    config_file = tmp_path / "pyproject.toml"
    config_file.write_text("""
[tool.golem.site]
title = "PyProject API Docs"

[tool.golem.api]
packages = ["pkg_a", "pkg_b"]
output_dir = "api_docs"
docstring_style = "sphinx"
""")
    config = load_config(config_file)
    assert config.api_packages == ["pkg_a", "pkg_b"]
    assert config.api_output_dir == "api_docs"
    assert config.api_docstring_style == "sphinx"


def test_config_api_alternative_keys_and_formats(tmp_path):
    # Test single string package and api_* prefixes in golem.toml
    config_file = tmp_path / "golem.toml"
    config_file.write_text("""
[api]
api_packages = "single_package"
api_output_dir = "custom_api"
api_docstring_style = "numpy"
""")
    config = load_config(config_file)
    assert config.api_packages == ["single_package"]
    assert config.api_output_dir == "custom_api"
    assert config.api_docstring_style == "numpy"

    # Test flattened [tool.golem] in pyproject.toml
    config_pyproject = tmp_path / "pyproject.toml"
    config_pyproject.write_text("""
[tool.golem]
api_packages = ["flat_pkg"]
api_output_dir = "flat_api"
api_docstring_style = "auto"
""")
    config_flat = load_config(config_pyproject)
    assert config_flat.api_packages == ["flat_pkg"]
    assert config_flat.api_output_dir == "flat_api"
    assert config_flat.api_docstring_style == "auto"


def test_resolve_plugins_raw():
    assert _resolve_plugins_raw({}) is None
    assert _resolve_plugins_raw({"plugins": ["p1", "p2"]}) == ["p1", "p2"]
    assert _resolve_plugins_raw({"plugins": {"plugins": ["p1"]}}) == ["p1"]
    assert _resolve_plugins_raw({"plugins": {"enabled": ["p2"]}}) == ["p2"]
    assert _resolve_plugins_raw({"plugins": "invalid_type"}) == "invalid_type"


def test_extract_config_values_defaults():
    values = _extract_config_values({}, {})
    assert values == {
        "site_title": "Golem Docs",
        "site_author": "Anonymous",
        "site_url": None,
        "strict": False,
        "content_dir": "content",
        "output_dir": "dist",
        "theme": "default",
        "templates_dir": "templates",
        "static_dir": "static",
        "plugins_dir": "plugins",
        "plugins": [],
        "navigation_nav": None,
        "api_packages": [],
        "api_output_dir": "api",
        "api_docstring_style": "auto",
    }


def test_extract_config_values_precedence():
    # 1. Section-scoped key beats root/fallback-level key
    section = {
        "site": {"title": "Section Title", "author": "Section Author", "url": "https://section.url"},
        "build": {"strict": False, "content_dir": "section_content", "output_dir": "section_dist", "theme": "sec_theme"},
        "title": "Root Title",
        "author": "Root Author",
        "url": "https://root.url",
        "strict": True,
        "content_dir": "root_content",
        "output_dir": "root_dist",
        "theme": "root_theme",
    }
    values = _extract_config_values(section, section)
    assert values["site_title"] == "Section Title"
    assert values["site_author"] == "Section Author"
    assert values["site_url"] == "https://section.url"
    assert values["strict"] is False
    assert values["content_dir"] == "section_content"
    assert values["output_dir"] == "section_dist"
    assert values["theme"] == "sec_theme"

    # 2. Canonical key name beats alias at same level
    section_alias = {
        "site": {"name": "Site Name", "site_url": "https://alias.url"},
        "api": {"api_packages": ["pkg1"], "api_output_dir": "out_api", "api_docstring_style": "google"},
    }
    values_alias = _extract_config_values(section_alias, section_alias)
    assert values_alias["site_title"] == "Site Name"
    assert values_alias["site_url"] == "https://alias.url"
    assert values_alias["api_packages"] == ["pkg1"]
    assert values_alias["api_output_dir"] == "out_api"
    assert values_alias["api_docstring_style"] == "google"

    # Canonical beats alias when both present
    section_both = {
        "site": {
            "title": "Canonical Title",
            "name": "Alias Name",
            "url": "https://canonical.url",
            "site_url": "https://alias.url",
        },
        "api": {
            "packages": ["canonical_pkg"],
            "api_packages": ["alias_pkg"],
            "output_dir": "can_out",
            "api_output_dir": "alias_out",
        },
    }
    values_both = _extract_config_values(section_both, section_both)
    assert values_both["site_title"] == "Canonical Title"
    assert values_both["site_url"] == "https://canonical.url"
    assert values_both["api_packages"] == ["canonical_pkg"]
    assert values_both["api_output_dir"] == "can_out"


def test_config_precedence_in_golem_and_pyproject(tmp_path):
    # Test identical precedence behavior in golem.toml vs pyproject.toml
    golem_toml = tmp_path / "golem.toml"
    golem_toml.write_text("""
title = "Root Title"
site_title = "Root Site Title Alias"
url = "https://root.url"

[site]
title = "Site Title"
url = "https://site.url"

[build]
strict = true
content_dir = "golem_docs"
output_dir = "golem_dist"

[api]
packages = ["pkg_golem"]
""")
    golem_cfg = load_config(golem_toml)
    assert golem_cfg.site_title == "Site Title"
    assert golem_cfg.site_url == "https://site.url"
    assert golem_cfg.strict is True
    assert golem_cfg.content_dir == "golem_docs"
    assert golem_cfg.output_dir == "golem_dist"
    assert golem_cfg.api_packages == ["pkg_golem"]

    pyproject_toml = tmp_path / "pyproject.toml"
    pyproject_toml.write_text("""
[tool.golem]
title = "Root Title"
site_title = "Root Site Title Alias"
url = "https://root.url"

[tool.golem.site]
title = "Site Title"
url = "https://site.url"

[tool.golem.build]
strict = true
content_dir = "golem_docs"
output_dir = "golem_dist"

[tool.golem.api]
packages = ["pkg_golem"]
""")
    pyproject_cfg = load_config(pyproject_toml)
    assert pyproject_cfg.site_title == "Site Title"
    assert pyproject_cfg.site_url == "https://site.url"
    assert pyproject_cfg.strict is True
    assert pyproject_cfg.content_dir == "golem_docs"
    assert pyproject_cfg.output_dir == "golem_dist"
    assert pyproject_cfg.api_packages == ["pkg_golem"]
