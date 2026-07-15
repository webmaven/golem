# tests/test_config.py
import pytest
from pathlib import Path
from golem.config import GolemConfig, load_config

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

