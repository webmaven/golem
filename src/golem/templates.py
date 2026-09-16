"""

This module handles loading and compiling physical Chameleon `.pt` templates
from disk or the built-in package skeleton template.
"""

from pathlib import Path
from typing import Any
from chameleon import PageTemplate
from golem.config import GolemConfig
from golem.highlighting import PYGMENTS_CSS

BUILTIN_SKELETON_PATH: Path = Path(__file__).parent / "templates" / "default" / "skeleton.pt"
_CACHED_SKELETON_TEMPLATE: PageTemplate | None = None


def _get_builtin_skeleton_template() -> PageTemplate:
    """Load and cache default package skeleton template from src/golem/templates/default/skeleton.pt."""
    global _CACHED_SKELETON_TEMPLATE
    if _CACHED_SKELETON_TEMPLATE is None:
        with open(BUILTIN_SKELETON_PATH, "r", encoding="utf-8") as f:
            _CACHED_SKELETON_TEMPLATE = PageTemplate(f.read())
    return _CACHED_SKELETON_TEMPLATE


class PageCompiler:
    """

    Compiles body fragments into complete HTML pages using Chameleon templates.

    === Examples

    [source,python]
    ----
    >>> from golem.config import GolemConfig
    >>> from golem.templates import PageCompiler
    >>> config = GolemConfig(output_dir="dist")
    >>> compiler = PageCompiler(config)
    >>> html = compiler.compile_page("Sample Page", "<p>Paragraph content</p>", "")
    >>> "<title>Sample Page</title>" in html or "Sample Page" in html
    True
    >>> "<p>Paragraph content</p>" in html
    True

    ----
    """

    def __init__(self, config: GolemConfig):
        """

        Initialize the compiler with a Golem configuration.
        """
        self.config = config
        self._disk_template_cache: dict[Path, tuple[float, PageTemplate]] = {}
        self._pkg_default_template = self._load_builtin_template()
        self.default_template = self._load_builtin_template()

    def _get_disk_template(self, template_path: Path) -> PageTemplate:
        """Load and cache a PageTemplate from disk with mtime invalidation.

        [parameters]
        `template_path` (Path):: Path to the template file on disk.

        [returns]
        `PageTemplate`:: Compiled Chameleon PageTemplate instance.
        """
        template_path = Path(template_path)
        mtime = template_path.stat().st_mtime
        if template_path in self._disk_template_cache:
            cached_mtime, cached_template = self._disk_template_cache[template_path]
            if cached_mtime == mtime:
                return cached_template

        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        template = PageTemplate(template_content)
        self._disk_template_cache[template_path] = (mtime, template)
        return template

    def _load_builtin_template(self) -> PageTemplate:
        """Load default package skeleton template from src/golem/templates/default/skeleton.pt."""
        return _get_builtin_skeleton_template()

    def compile_page(
        self,
        title: str = "",
        body_html: str = "",
        toc_html: str = "",
        template_path: Path | None = None,
        nav_html: str = "",
        nav_tree: list[dict] | None = None,
        current_path: str = "",
        custom_css: list[str] | None = None,
        custom_js: list[str] | None = None,
        prev_page: dict[str, str] | None = None,
        next_page: dict[str, str] | None = None,
        body_class: str = "",
        content_class: str = "",
        pygments_css: str | None = None,
        **extra_context: Any,
    ) -> str:
        """

        Compile a full static page.

        === Arguments

        - `title`:: Document title.
        - `body_html`:: Processed HTML body text.
        - `toc_html`:: Rendered Table of Contents HTML.
        - `template_path`:: Optional layout override path.
        - `nav_html`:: Rendered left navigation HTML.
        - `nav_tree`:: Hierarchical site map navigation tree.
        - `current_path`:: Current document path relative to content dir.
        - `custom_css`:: Custom CSS stylesheet links to inject.
        - `custom_js`:: Custom JS script links to inject.
        - `prev_page`:: Previous document metadata for pagination.
        - `next_page`:: Next document metadata for pagination.
        - `body_class`:: CSS classes applied to the `<body>` element.
        - `content_class`:: Additional CSS classes applied to `<main id="golem-content">`.
        - `pygments_css`:: Optional custom Pygments CSS string to inject into the template.
        - `**extra_context`:: Additional context variables injected by plugins or custom callers.
        """
        for forbidden in ("body_content", "page_title", "page_class"):
            if forbidden in extra_context:
                raise TypeError(f"compile_page() got an unexpected keyword argument '{forbidden}'")

        effective_body_class = (body_class or "").strip()
        effective_content_class = (content_class or "").strip()
        effective_pygments_css = pygments_css if pygments_css is not None else PYGMENTS_CSS

        # Compute a depth-relative path back to the site root so the header
        # home-link works at any deployment base path (e.g. /golem/ on GitHub
        # Pages), without requiring a site_url to be configured.
        from pathlib import PurePosixPath

        _depth = len(PurePosixPath(current_path).parent.parts) if current_path else 0
        root_path = ("../" * _depth) if _depth else "./"

        import golem

        generator_version = getattr(golem, "__version__", "0.1.0a2")

        if template_path is not None:
            template = self._get_disk_template(template_path)
        else:
            # Check for user's scaffolded custom templates directory first
            user_pt = Path(self.config.templates_dir) / "page.pt" if getattr(self.config, "templates_dir", None) else None
            if user_pt and user_pt.exists():
                template = self._get_disk_template(user_pt)
            else:
                # Fallback to configured themes folder override if exists
                theme_dir = Path("themes") / self.config.theme
                skeleton_pt = theme_dir / "skeleton.pt"
                if skeleton_pt.exists():
                    template = self._get_disk_template(skeleton_pt)
                else:
                    template = self.default_template

        try:
            default_layout = self.default_template.macros["layout"]
        except (KeyError, AttributeError):
            try:
                default_layout = self._pkg_default_template.macros["layout"]
            except (KeyError, AttributeError):
                default_layout = None

        template_kwargs: dict[str, Any] = {
            "title": title,
            "body_html": body_html,
            "toc_html": toc_html,
            "nav_html": nav_html,
            "nav_tree": nav_tree or [],
            "current_path": current_path,
            "prev_page": prev_page,
            "next_page": next_page,
            "site_title": getattr(self.config, "site_title", "Golem Docs"),
            "site_author": getattr(self.config, "site_author", "Anonymous"),
            "site_url": getattr(self.config, "site_url", None),
            "root_path": root_path,
            "generator_version": generator_version,
            "custom_css": custom_css or [],
            "custom_js": custom_js or [],
            "body_class": effective_body_class,
            "content_class": effective_content_class,
            "pygments_css": effective_pygments_css,
            "default_layout": default_layout,
        }
        template_kwargs.update(extra_context)

        return template(**template_kwargs)
