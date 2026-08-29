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
    `quiet` (bool):: Whether quiet mode is enabled to suppress progress output. Defaults to `False`.
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
    quiet: bool = False
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


def _resolve_plugins_raw(section: dict[str, Any]) -> Any:
    """Resolve the raw plugins value from either list or sub-dict form.

    [parameters]
    `section` (dict[str, Any]):: Golem configuration section or document dictionary.

    [returns]
    `Any`:: Raw plugins structure (list, dictionary, string, or None).
    """
    plugins_data = section.get("plugins")
    if isinstance(plugins_data, dict):
        return plugins_data.get("plugins") or plugins_data.get("enabled")
    return plugins_data


def _extract_config_values(section: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """Normalize a golem config section into a flat dict for GolemConfig construction.

    `section` is the golem-specific table (`data["tool"]["golem"]` or `data` for `golem.toml`).
    `root` is the full TOML document (used for root-level key fallbacks in `golem.toml`).

    [parameters]
    `section` (dict[str, Any]):: Golem-specific configuration dictionary table.
    `root` (dict[str, Any]):: Full raw TOML document dictionary for root fallback resolution.

    [returns]
    `dict[str, Any]`:: Flat dictionary containing normalized configuration parameters.
    """
    site = section.get("site", {}) if isinstance(section.get("site"), dict) else {}
    build = section.get("build", {}) if isinstance(section.get("build"), dict) else {}
    nav = section.get("navigation", {}) if isinstance(section.get("navigation"), dict) else {}
    api = section.get("api", {}) if isinstance(section.get("api"), dict) else {}

    return {
        "site_title": (
            site.get("title") or site.get("name") or section.get("title") or section.get("site_title") or "Golem Docs"
        ),
        "site_author": (site.get("author") or section.get("author") or section.get("site_author") or "Anonymous"),
        "site_url": (site.get("url") or site.get("site_url") or section.get("url") or section.get("site_url") or None),
        "strict": bool(build.get("strict", section.get("strict", False))),
        "quiet": bool(build.get("quiet", section.get("quiet", False))),
        "content_dir": build.get("content_dir") or section.get("content_dir") or "content",
        "output_dir": build.get("output_dir") or section.get("output_dir") or "dist",
        "theme": build.get("theme") or section.get("theme") or "default",
        "templates_dir": build.get("templates_dir") or section.get("templates_dir") or "templates",
        "static_dir": build.get("static_dir") or section.get("static_dir") or "static",
        "plugins_dir": build.get("plugins_dir") or section.get("plugins_dir") or "plugins",
        "plugins": _parse_plugins(_resolve_plugins_raw(section)) or [],
        "navigation_nav": _parse_nav(nav.get("nav") or section.get("nav")),
        "api_packages": _parse_api_packages(
            api.get("packages")
            or api.get("api_packages")
            or section.get("api_packages")
            or (section.get("api") if isinstance(section.get("api"), (list, str)) else None)
        ),
        "api_output_dir": (api.get("output_dir") or api.get("api_output_dir") or section.get("api_output_dir") or "api"),
        "api_docstring_style": (
            api.get("docstring_style") or api.get("api_docstring_style") or section.get("api_docstring_style") or "auto"
        ),
    }


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
        section = data.get("tool", {}).get("golem", {})
    else:
        section = data

    values = _extract_config_values(section, data)

    # Ensure resolved content_dir and output_dir do not overlap (identical or nested)
    content_dir = values["content_dir"]
    output_dir = values["output_dir"]
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
        **values,
        config_path=str(config_path.resolve()),
    )
