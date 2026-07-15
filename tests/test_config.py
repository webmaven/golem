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
