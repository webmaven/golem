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
    pyproject.write_text("[tool.poetry]\nname = \"test\"")
    assert find_default_config_path() == Path("golem.toml")

    # 3. pyproject.toml exists with [tool.golem] -> should return pyproject.toml
    pyproject.write_text("[tool.golem]\ntitle = \"Test\"")
    assert find_default_config_path() == Path("pyproject.toml")

    # 4. Both exist -> should prefer golem.toml
    golem = tmp_path / "golem.toml"
    golem.write_text("")
    assert find_default_config_path() == Path("golem.toml")


