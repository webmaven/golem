# golem/config.py
"""
Configuration loading and resolution for Golem static site builds.

Configuration is read from either a dedicated ``golem.toml`` at the
project root or from the ``[tool.golem]`` table inside a standard
``pyproject.toml``.  Discovery order (handled by
:func:`find_default_config_path`) is:

1. ``golem.toml`` in the current working directory (always preferred).
2. ``pyproject.toml`` in the current working directory, provided it
   contains a ``[tool.golem]`` table.
3. ``golem.toml`` as a fallback sentinel path (callers must check
   existence themselves).

:func:`load_config` parses whichever file is found, normalises every
key with sensible defaults, validates that ``content_dir`` and
``output_dir`` do not overlap, and returns a fully-populated
:class:`GolemConfig` dataclass.

Internal helpers ``_parse_nav``, ``_parse_plugins``, and
``_parse_api_packages`` accept the raw TOML value (which may arrive as
a list of strings, a list of ``{path/name: …}`` dicts, or ``None``) and
return a clean Python list, so the rest of the codebase never has to
handle the TOML polymorphism directly.
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
    """Runtime configuration for a Golem build.

    All fields carry defaults so that an in-code ``GolemConfig()`` with no
    arguments produces a working configuration for a project that has not
    yet written a config file.

    === Fields

    ``site_title``::
        Human-readable site name used in ``<title>`` elements and the top
        navigation bar.  Default: ``"Golem Docs"``.

    ``site_author``::
        Primary author credit, exposed to templates and API doc headers.
        Default: ``"Anonymous"``.

    ``site_url``::
        Canonical base URL (e.g. ``"https://example.com/docs/"``).
        ``None`` when unset; templates should omit canonical ``<link>``
        elements in that case.

    ``strict``::
        When ``True``, any AsciiDoc parse warning is promoted to a build
        error that terminates the process with a non-zero exit code.
        Default: ``False``.

    ``navigation_nav``::
        Ordered list of content-relative paths that override the
        automatically-discovered navigation tree.  ``None`` means
        auto-discover.

    ``content_dir``::
        Source directory containing ``.adoc`` files.  Relative to the
        project root (the directory from which ``golem`` is invoked).
        Default: ``"content"``.

    ``output_dir``::
        Directory into which rendered HTML is written.  Must not overlap
        with ``content_dir``.  Default: ``"dist"``.

    ``theme``::
        Name of the built-in or project-local theme to use for template
        resolution.  Default: ``"default"``.

    ``templates_dir``::
        Project-local directory for Chameleon template overrides.
        Default: ``"templates"``.

    ``static_dir``::
        Directory of static assets (CSS, images, fonts) copied verbatim
        into ``output_dir``.  Default: ``"static"``.

    ``plugins_dir``::
        Directory scanned for local Pluggy plugin ``.py`` files.
        Default: ``"plugins"``.

    ``plugins``::
        List of fully-qualified Python module names (e.g.
        ``"golem.plugins.apidoc"``) to load as Pluggy plugins in addition
        to entry-point discovery.  Default: empty list.

    ``api_packages``::
        List of importable top-level package names whose public API is
        extracted by the ``apidoc`` plugin.  Default: empty list.

    ``api_output_dir``::
        Sub-directory (relative to ``output_dir``) where generated API
        reference pages are written.  Default: ``"api"``.

    ``api_docstring_style``::
        Docstring format hint passed to Griffe for parsing — one of
        ``"auto"``, ``"google"``, ``"numpy"``, or ``"sphinx"``.
        Default: ``"auto"``.

    ``config_path``::
        Absolute path of the config file that was loaded, stored as a
        string so that templates and error messages can reference it.
        ``None`` when configuration was constructed programmatically.
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
    """Locate the best available configuration file for the current project.

    Searches the current working directory in priority order:

    1. ``golem.toml`` — returned immediately if it exists.
    2. ``pyproject.toml`` — returned if it exists *and* contains a
       ``[tool.golem]`` table; malformed TOML is silently skipped.
    3. ``golem.toml`` as a sentinel fallback (may not exist; callers are
       expected to handle the missing-file case via :func:`load_config`).

    === Returns

    :class:`~pathlib.Path` to the candidate config file.  The caller must
    check :attr:`~pathlib.Path.exists` if the fallback sentinel was
    returned.
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
    """Normalise a raw TOML navigation value into a flat list of path strings.

    Accepts the polymorphic TOML representations that Golem supports:

    * ``None`` — no nav override; returns ``None``.
    * A list of plain strings — returned as-is.
    * A list of ``{"path": "..."}`` dicts (TOML inline-table style) —
      each ``path`` value is extracted.
    * Any other item type is coerced to ``str``.

    === Arguments

    - ``raw_nav``:: Raw value from ``[tool.golem.navigation]`` or the
      top-level ``nav`` key in ``golem.toml``.

    === Returns

    Flat ``list[str]`` of relative content paths, or ``None`` if the
    input was ``None`` or not a list.
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
    """Normalise a raw TOML plugins value into a flat list of module-name strings.

    Accepts the polymorphic TOML representations that Golem supports:

    * ``None`` — no plugins configured; returns ``None``.
    * A list of plain strings — returned as-is.
    * A list of ``{"name": "..."}`` dicts — each ``name`` value is extracted.
    * Any other item type is coerced to ``str``.

    === Arguments

    - ``raw_plugins``:: Raw value from ``[tool.golem.plugins]`` or the
      top-level ``plugins`` key in ``golem.toml``.

    === Returns

    Flat ``list[str]`` of fully-qualified Python module names (e.g.
    ``"golem.plugins.apidoc"``), or ``None`` if the input was ``None``
    or not a list.
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
    """Normalise a raw TOML API packages value into a flat list of package-name strings.

    Accepts the polymorphic TOML representations that Golem supports:

    * ``None`` — no packages configured; returns ``[]``.
    * A plain string — wrapped in a single-element list.
    * A list of plain strings — returned as-is.
    * A list of ``{"name": "..."}`` dicts — each ``name`` value is extracted.
    * Any other item type is coerced to ``str``.

    === Arguments

    - ``raw_packages``:: Raw value from ``[tool.golem.api]`` ``packages``
      key or its legacy aliases.

    === Returns

    Flat ``list[str]`` of importable top-level package names.  Always
    returns a list (never ``None``).
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
    """Parse a Golem config file and return a fully-validated :class:`GolemConfig`.

    Reads TOML from *config_path*, auto-detecting whether it is a
    ``golem.toml`` (top-level ``[site]``/``[build]``/… tables) or a
    ``pyproject.toml`` (``[tool.golem.*]`` tables).  All keys are
    normalised with sensible defaults so the caller never receives
    ``None`` where a list or string is expected.

    If *config_path* does not exist, a default :class:`GolemConfig` is
    returned immediately (equivalent to ``GolemConfig()``).

    === Arguments

    - ``config_path``:: :class:`~pathlib.Path` to ``golem.toml`` or
      ``pyproject.toml``.  Typically produced by
      :func:`find_default_config_path`.

    === Returns

    A populated :class:`GolemConfig` instance.

    === Raises

    ``ValueError``
        If the TOML file cannot be parsed, or if ``content_dir`` and
        ``output_dir`` resolve to overlapping filesystem paths (identical,
        or one nested inside the other).
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
