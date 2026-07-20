# golem/config.py
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]
from dataclasses import dataclass
from pathlib import Path

@dataclass
class GolemConfig:
    site_title: str = "Golem Docs"
    site_author: str = "Anonymous"
    content_dir: str = "content"
    output_dir: str = "dist"
    theme: str = "default"
    templates_dir: str = "templates"
    static_dir: str = "static"
    plugins_dir: str = "plugins"
    config_path: str | None = None


def find_default_config_path() -> Path:
    golem_toml = Path("golem.toml")
    if golem_toml.exists():
        return golem_toml
    pyproject_toml = Path("pyproject.toml")
    if pyproject_toml.exists():
        try:
            with open(pyproject_toml, "rb") as f:
                data = tomllib.load(f)
            if "tool" in data and "golem" in data["tool"]:
                return pyproject_toml
        except Exception:
            pass
    return golem_toml


def load_config(config_path: Path) -> GolemConfig:
    if not config_path.exists():
        return GolemConfig()
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse configuration file '{config_path}': {e}")

    # Check if this is a pyproject.toml file
    if config_path.name == "pyproject.toml":
        golem_data = data.get("tool", {}).get("golem", {})
        site_data = golem_data.get("site", {})
        build_data = golem_data.get("build", {})
        
        site_title = site_data.get("title") or golem_data.get("title") or golem_data.get("site_title") or "Golem Docs"
        site_author = site_data.get("author") or golem_data.get("author") or golem_data.get("site_author") or "Anonymous"
        content_dir = build_data.get("content_dir") or golem_data.get("content_dir") or "content"
        output_dir = build_data.get("output_dir") or golem_data.get("output_dir") or "dist"
        theme = build_data.get("theme") or golem_data.get("theme") or "default"
        
        templates_dir = build_data.get("templates_dir") or golem_data.get("templates_dir") or "templates"
        static_dir = build_data.get("static_dir") or golem_data.get("static_dir") or "static"
        plugins_dir = build_data.get("plugins_dir") or golem_data.get("plugins_dir") or "plugins"
    else:
        site_data = data.get("site", {})
        build_data = data.get("build", {})
        site_title = site_data.get("title", "Golem Docs")
        site_author = site_data.get("author", "Anonymous")
        content_dir = build_data.get("content_dir", "content")
        output_dir = build_data.get("output_dir", "dist")
        theme = build_data.get("theme", "default")
        
        templates_dir = build_data.get("templates_dir", "templates")
        static_dir = build_data.get("static_dir", "static")
        plugins_dir = build_data.get("plugins_dir", "plugins")

    # Ensure resolved content_dir and output_dir do not overlap (identical or nested)
    try:
        content_abs = Path(content_dir).resolve()
        output_abs = Path(output_dir).resolve()
    except Exception:
        content_abs = Path(content_dir).absolute()
        output_abs = Path(output_dir).absolute()

    if content_abs == output_abs:
        raise ValueError(f"Configuration conflict: content_dir '{content_dir}' and output_dir '{output_dir}' cannot be the same path (they overlap).")

    if content_abs in output_abs.parents:
        raise ValueError(f"Configuration conflict: content_dir '{content_dir}' cannot be nested inside output_dir '{output_dir}' (they overlap).")

    if output_abs in content_abs.parents:
        raise ValueError(f"Configuration conflict: output_dir '{output_dir}' cannot be nested inside content_dir '{content_dir}' (they overlap).")

    return GolemConfig(
        site_title=site_title,
        site_author=site_author,
        content_dir=content_dir,
        output_dir=output_dir,
        theme=theme,
        templates_dir=templates_dir,
        static_dir=static_dir,
        plugins_dir=plugins_dir,
        config_path=str(config_path.resolve()),
    )

