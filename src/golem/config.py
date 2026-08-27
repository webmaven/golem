"""Manage configuration discovery, loading, parsing, and data models for Golem.

== Configuration Discovery

Golem locates site configuration by checking the local directory:
1. `golem.toml` is prioritized if present.
2. `pyproject.toml` is inspected for a `[tool.golem]` section if `golem.toml` is absent.
3. If neither configuration file is found, defaults are loaded targeting `golem.toml`.

== Configuration Structure

Configuration options can be organized in `golem.toml` or `pyproject.toml`:

`[site]` / `[tool.golem.site]`:: Defines site metadata such as `title`, `author`, and base `url`.
`[build]` / `[tool.golem.build]`:: Configures build settings including `content_dir`, `output_dir`, `theme`, `templates_dir`, `static_dir`, `plugins_dir`, and `strict` mode.
`[navigation]` / `[tool.golem.navigation]`:: Declares custom navigation order and page lists via `nav`.
`[api]` / `[tool.golem.api]`:: Configures API documentation generation including target `packages`, `output_dir`, and `docstring_style`.
`[plugins]` / `[tool.golem.plugins]`:: Declares plugin extensions via `plugins` or `enabled` lists.

Flattened keys directly under `[tool.golem]` in `pyproject.toml` or top-level keys in `golem.toml` are also supported.

== Configuration Lifecycle

1. Discovery: `find_default_config_path()` identifies the active configuration file.
2. Loading & Parsing: `load_config()` reads TOML data via `tomllib` or `tomli` fallback and normalizes nested tables.
3. Validation: Directory paths are checked to prevent overlapping or nested `content_dir` and `output_dir` targets.
4. Instantiation: A typed `GolemConfig` instance is created and passed to the build engine, CLI, and plugins.
"""

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GolemConfig:
    """Store site configuration and build parameters for Golem.

    Holds resolved site metadata, build flags, filesystem directory locations,
    navigation structures, plugin configurations, and API documentation options.

    [attributes]
    `site_title` (str):: Title of the documentation site. Defaults to `"Golem Docs"`.
    `site_author` (str):: Author or organization name for the site metadata. Defaults to `"Anonymous"`.
    `site_url` (str | None):: Canonical base URL where the site is hosted. Defaults to `None`.
    `strict` (bool):: Whether strict build mode is enabled to fail on warnings. Defaults to `False`.
    `navigation_nav` (list[str] | None):: Ordered list of content page paths for site navigation. Defaults to `None`.
    `content_dir` (str):: Directory path containing source content files. Defaults to `"content"`.
    `output_dir` (str):: Directory path where compiled static output is generated. Defaults to `"dist"`.
    `theme` (str):: Name of the site theme to apply. Defaults to `"default"`.
    `templates_dir` (str):: Directory path containing custom Jinja HTML templates. Defaults to `"templates"`.
    `static_dir` (str):: Directory path containing static asset files. Defaults to `"static"`.
    `plugins_dir` (str):: Directory path containing custom plugin definitions. Defaults to `"plugins"`.
    `plugins` (list[str]):: List of enabled plugin module names or paths. Defaults to `[]`.
    `api_packages` (list[str]):: List of Python package or module names to document. Defaults to `[]`.
    `api_output_dir` (str):: Output subdirectory within `output_dir` for generated API reference docs. Defaults to `"api"`.
    `api_docstring_style` (str):: Docstring parser style (`"auto"`, `"asciidoc"`, `"google"`, `"numpy"`, or `"sphinx"`). Defaults to `"auto"`.
    `config_path` (str | None):: Absolute path to the resolved configuration file used. Defaults to `None`.
    """

    site_title: str = "Golem Docs"
    site_author: str = "Anonymous"
    site_url: str | None = None
    strict: bool = False
    navigation_nav: list[str] | None = None
    content_dir: str = "content"
    output_dir: str = "dist"
    theme: str = "default"
    templates_dir: str = "templates"
    static_dir: str = "static"
    plugins_dir: str = "plugins"
    plugins: list[str] = field(default_factory=list)
    api_packages: list[str] = field(default_factory=list)
    api_output_dir: str = "api"
    api_docstring_style: str = "auto"
    config_path: str | None = None


def find_default_config_path() -> Path:
    """Locate the default configuration file path in the workspace.

    Searches for `golem.toml` first, then inspects `pyproject.toml` for a `[tool.golem]`
    section. If neither file exists or if `pyproject.toml` lacks Golem configuration,
    defaults to returning `golem.toml`.

    [returns]
    `Path`:: Path to the discovered `golem.toml` or `pyproject.toml` configuration file.
    """
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


def _parse_nav(raw_nav: Any) -> list[str] | None:
    """Parse raw navigation configuration into a list of relative page paths.

    Extracts path strings from lists of strings or dictionaries containing a `'path'` key.

    [parameters]
    `raw_nav` (Any):: Raw navigation data structure loaded from TOML configuration.

    [returns]
    `list[str] | None`:: List of relative page paths, or `None` if navigation is not specified or invalid.
    """
    if raw_nav is None:
        return None
    if isinstance(raw_nav, list):
        parsed = []
        for item in raw_nav:
            if isinstance(item, dict) and "path" in item:
                parsed.append(str(item["path"]))
            elif isinstance(item, str):
                parsed.append(item)
            else:
                parsed.append(str(item))
        return parsed
    return None


def _parse_plugins(raw_plugins: Any) -> list[str] | None:
    """Parse raw plugin configuration into a list of plugin module names.

    Extracts plugin identifiers from lists of strings or dictionaries containing a `'name'` key.

    [parameters]
    `raw_plugins` (Any):: Raw plugin data structure loaded from TOML configuration.

    [returns]
    `list[str] | None`:: List of plugin module names, or `None` if plugins are not specified or invalid.
    """
    if raw_plugins is None:
        return None
    if isinstance(raw_plugins, list):
        parsed = []
        for item in raw_plugins:
            if isinstance(item, dict) and "name" in item:
                parsed.append(str(item["name"]))
            elif isinstance(item, str):
                parsed.append(item)
            else:
                parsed.append(str(item))
        return parsed
    return None


def _parse_api_packages(raw_packages: Any) -> list[str]:
    """Parse raw API package configuration into a list of package or module names.

    Accepts single strings, lists of strings, or lists of dictionaries containing a `'name'` key.

    [parameters]
    `raw_packages` (Any):: Raw API package configuration loaded from TOML.

    [returns]
    `list[str]`:: List of normalized package or module names. Defaults to an empty list if unspecified.
    """
    if raw_packages is None:
        return []
    if isinstance(raw_packages, str):
        return [raw_packages]
    if isinstance(raw_packages, list):
        parsed = []
        for item in raw_packages:
            if isinstance(item, dict) and "name" in item:
                parsed.append(str(item["name"]))
            elif isinstance(item, str):
                parsed.append(item)
            else:
                parsed.append(str(item))
        return parsed
    return []


def load_config(config_path: Path) -> GolemConfig:
    """Load, parse, and validate Golem site configuration from a TOML file.

    Supports reading configuration from standalone `golem.toml` files or `pyproject.toml`
    under the `[tool.golem]` table. Validates that `content_dir` and `output_dir` do not
    overlap or nest inside one another.

    [parameters]
    `config_path` (Path):: Path to the TOML configuration file to load.

    [returns]
    `GolemConfig`:: Fully populated configuration dataclass instance with default fallbacks.

    [raises]
    `ValueError`:: If TOML syntax is invalid or if `content_dir` and `output_dir` paths overlap.
    """
    if not config_path.exists():
        return GolemConfig()
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse configuration file '{config_path}': {e}")

    # Check if this is a pyproject.toml file
    if config_path.name == "pyproject.toml" or ("tool" in data and "golem" in data.get("tool", {})):
        golem_data = data.get("tool", {}).get("golem", {})
        site_data = golem_data.get("site", {})
        build_data = golem_data.get("build", {})
        nav_data = golem_data.get("navigation", {})

        site_title = (
            site_data.get("title")
            or site_data.get("name")
            or golem_data.get("title")
            or golem_data.get("site_title")
            or "Golem Docs"
        )
        site_author = site_data.get("author") or golem_data.get("author") or golem_data.get("site_author") or "Anonymous"
        site_url = (
            site_data.get("url") or golem_data.get("url") or golem_data.get("site_url") or site_data.get("site_url") or None
        )
        strict = bool(build_data.get("strict") if "strict" in build_data else golem_data.get("strict", False))
        content_dir = build_data.get("content_dir") or golem_data.get("content_dir") or "content"
        output_dir = build_data.get("output_dir") or golem_data.get("output_dir") or "dist"
        theme = build_data.get("theme") or golem_data.get("theme") or "default"

        templates_dir = build_data.get("templates_dir") or golem_data.get("templates_dir") or "templates"
        static_dir = build_data.get("static_dir") or golem_data.get("static_dir") or "static"
        plugins_dir = build_data.get("plugins_dir") or golem_data.get("plugins_dir") or "plugins"
        plugins_data = golem_data.get("plugins")
        if isinstance(plugins_data, dict):
            raw_plugins = plugins_data.get("plugins") if "plugins" in plugins_data else plugins_data.get("enabled")
        else:
            raw_plugins = plugins_data
        parsed_plugins = _parse_plugins(raw_plugins)
        plugins = parsed_plugins if parsed_plugins is not None else []
        raw_nav = nav_data.get("nav") if "nav" in nav_data else (golem_data.get("navigation_nav") or golem_data.get("nav"))
        navigation_nav = _parse_nav(raw_nav)

        api_data = golem_data.get("api", {}) if isinstance(golem_data.get("api"), dict) else {}
        raw_api_packages = (
            api_data.get("packages")
            if "packages" in api_data
            else (
                api_data.get("api_packages")
                if "api_packages" in api_data
                else (
                    golem_data.get("api_packages")
                    or (golem_data.get("api") if isinstance(golem_data.get("api"), (list, str)) else None)
                )
            )
        )
        api_packages = _parse_api_packages(raw_api_packages)
        api_output_dir = (
            api_data.get("output_dir") or api_data.get("api_output_dir") or golem_data.get("api_output_dir") or "api"
        )
        api_docstring_style = (
            api_data.get("docstring_style")
            or api_data.get("api_docstring_style")
            or golem_data.get("api_docstring_style")
            or "auto"
        )
    else:
        site_data = data.get("site", {})
        build_data = data.get("build", {})
        nav_data = data.get("navigation", {})

        site_title = site_data.get("title") or site_data.get("name") or "Golem Docs"
        site_author = site_data.get("author", "Anonymous")
        site_url = site_data.get("url") or data.get("site_url") or site_data.get("site_url") or data.get("url") or None
        strict = bool(build_data.get("strict") if "strict" in build_data else data.get("strict", False))
        content_dir = build_data.get("content_dir", "content")
        output_dir = build_data.get("output_dir", "dist")
        theme = build_data.get("theme", "default")

        templates_dir = build_data.get("templates_dir", "templates")
        static_dir = build_data.get("static_dir") or data.get("static_dir") or "static"
        plugins_dir = build_data.get("plugins_dir", "plugins")
        plugins_data = data.get("plugins")
        if isinstance(plugins_data, dict):
            raw_plugins = plugins_data.get("plugins") if "plugins" in plugins_data else plugins_data.get("enabled")
        else:
            raw_plugins = plugins_data
        parsed_plugins = _parse_plugins(raw_plugins)
        plugins = parsed_plugins if parsed_plugins is not None else []
        raw_nav = (
            nav_data.get("nav")
            if "nav" in nav_data
            else (data.get("navigation_nav") if "navigation_nav" in data else data.get("nav"))
        )
        navigation_nav = _parse_nav(raw_nav)

        api_data = data.get("api", {}) if isinstance(data.get("api"), dict) else {}
        raw_api_packages = (
            api_data.get("packages")
            if "packages" in api_data
            else (
                api_data.get("api_packages")
                if "api_packages" in api_data
                else (data.get("api_packages") or (data.get("api") if isinstance(data.get("api"), (list, str)) else None))
            )
        )
        api_packages = _parse_api_packages(raw_api_packages)
        api_output_dir = api_data.get("output_dir") or api_data.get("api_output_dir") or data.get("api_output_dir") or "api"
        api_docstring_style = (
            api_data.get("docstring_style") or api_data.get("api_docstring_style") or data.get("api_docstring_style") or "auto"
        )

    # Ensure resolved content_dir and output_dir do not overlap (identical or nested)
    try:
        content_abs = Path(content_dir).resolve()
        output_abs = Path(output_dir).resolve()
    except Exception:
        content_abs = Path(content_dir).absolute()
        output_abs = Path(output_dir).absolute()

    if content_abs == output_abs:
        raise ValueError(
            f"Configuration conflict: content_dir '{content_dir}' and output_dir '{output_dir}' cannot be the same path (they overlap)."
        )

    if content_abs in output_abs.parents:
        raise ValueError(
            f"Configuration conflict: content_dir '{content_dir}' cannot be nested inside output_dir '{output_dir}' (they overlap)."
        )

    if output_abs in content_abs.parents:
        raise ValueError(
            f"Configuration conflict: output_dir '{output_dir}' cannot be nested inside content_dir '{content_dir}' (they overlap)."
        )

    return GolemConfig(
        site_title=site_title,
        site_author=site_author,
        site_url=site_url,
        strict=strict,
        navigation_nav=navigation_nav,
        content_dir=content_dir,
        output_dir=output_dir,
        theme=theme,
        templates_dir=templates_dir,
        static_dir=static_dir,
        plugins_dir=plugins_dir,
        plugins=plugins,
        api_packages=api_packages,
        api_output_dir=api_output_dir,
        api_docstring_style=api_docstring_style,
        config_path=str(config_path.resolve()),
    )
