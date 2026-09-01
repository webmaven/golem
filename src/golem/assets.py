"""Provide static asset synchronization for Golem builds.

== Asset Layering Architecture

Golem synchronizes static assets into the output `<output_dir>/static` directory using
a hierarchical fallback and override order:
1. Package default theme static assets (`golem/templates/<theme>/static` and `golem/templates/default/static`).
2. Workspace theme static assets (`themes/<theme>/static`).
3. Custom templates static assets (`<templates_dir>/static`).
4. User project static assets (`<static_dir>`).

Additionally, non-AsciiDoc media and static assets located within the project `content_dir`
(such as images, SVGs, diagrams, PDFs, and downloadable attachments) are synchronized
directly into `output_dir`, preserving relative directory structures.
"""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any

__all__ = [
    "sync_static_assets",
]


def sync_static_assets(config: Any, content_dir: Path, output_dir: Path) -> None:
    """Synchronize static assets from package defaults, theme directories, and user static folders.

    Copies assets into `<output_dir>/static` in layered precedence order:
    1. Package default theme static assets (`golem/templates/<theme>/static` and `golem/templates/default/static`).
    2. Workspace theme static assets (`themes/<theme>/static`).
    3. Custom templates static assets (`<templates_dir>/static`).
    4. User project static assets (`<static_dir>`).

    Additionally synchronizes non-AsciiDoc media and static assets located within
    `content_dir` directly into `output_dir`, preserving relative directory paths.

    Higher-precedence assets overwrite lower-precedence assets with matching relative paths.

    [parameters]
    `config` (Any):: Site configuration object specifying `theme`, `static_dir`, and `templates_dir`.
    `content_dir` (Path):: Path to the source documentation content directory.
    `output_dir` (Path):: Path to the build target output directory.

    [returns]
    `None`:: Static assets are copied directly to disk.

    === Examples

    [source,python]
    ----
    >>> from pathlib import Path
    >>> import tempfile
    >>> from golem.config import GolemConfig
    >>> from golem.assets import sync_static_assets
    >>> with tempfile.TemporaryDirectory() as tmp_dir:
    ...     tmp = Path(tmp_dir)
    ...     c_dir = tmp / "content"
    ...     c_dir.mkdir()
    ...     _ = (c_dir / "logo.png").write_bytes(b"data")
    ...     o_dir = tmp / "dist"
    ...     config = GolemConfig(content_dir=str(c_dir), output_dir=str(o_dir))
    ...     sync_static_assets(config, c_dir, o_dir)
    ...     (o_dir / "logo.png").exists()
    True
    ----
    """
    output_dir = Path(output_dir)
    content_dir = Path(content_dir)
    output_static_dir = output_dir / "static"

    theme_name = getattr(config, "theme", "default") or "default"

    # 1. Package default theme static assets (if any)
    pkg_theme_static = Path(__file__).parent / "templates" / theme_name / "static"
    if pkg_theme_static.exists() and pkg_theme_static.is_dir():
        output_static_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(pkg_theme_static, output_static_dir, dirs_exist_ok=True)

    # Also check package default static if theme != default
    pkg_default_static = Path(__file__).parent / "templates" / "default" / "static"
    if pkg_default_static != pkg_theme_static and pkg_default_static.exists() and pkg_default_static.is_dir():
        output_static_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(pkg_default_static, output_static_dir, dirs_exist_ok=True)

    # 2. Configured theme directory static assets (themes/<theme>/static)
    if theme_name:
        theme_static = Path("themes") / theme_name / "static"
        if theme_static.exists() and theme_static.is_dir():
            output_static_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(theme_static, output_static_dir, dirs_exist_ok=True)

    # Custom templates_dir static (if configured)
    if hasattr(config, "templates_dir") and config.templates_dir:
        tpl_static = Path(config.templates_dir) / "static"
        if tpl_static.exists() and tpl_static.is_dir():
            output_static_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(tpl_static, output_static_dir, dirs_exist_ok=True)

    # 3. User static_dir (e.g. static/)
    if hasattr(config, "static_dir") and config.static_dir:
        user_static = Path(config.static_dir)
        if user_static.exists() and user_static.is_dir():
            output_static_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(user_static, output_static_dir, dirs_exist_ok=True)

    # 4. Content directory static assets (images, attachments, non-AsciiDoc media)
    if content_dir.exists() and content_dir.is_dir():
        for item in content_dir.rglob("*"):
            if item.is_file() and item.suffix != ".adoc" and not item.name.startswith("."):
                rel = item.relative_to(content_dir)
                dest = output_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
