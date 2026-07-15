# golem/config.py
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

@dataclass
class GolemConfig:
    site_title: str = "Golem Docs"
    site_author: str = "Anonymous"
    content_dir: str = "content"
    output_dir: str = "dist"
    theme: str = "default"

def load_config(config_path: Path) -> GolemConfig:
    if not config_path.exists():
        return GolemConfig()
    with open(config_path, "rb") as f:
        data = tomllib.load(f)
    site_data = data.get("site", {})
    build_data = data.get("build", {})
    return GolemConfig(
        site_title=site_data.get("title", "Golem Docs"),
        site_author=site_data.get("author", "Anonymous"),
        content_dir=build_data.get("content_dir", "content"),
        output_dir=build_data.get("output_dir", "dist"),
        theme=build_data.get("theme", "default"),
    )
