"""
= Page Layout Compilation

This module handles loading and compiling physical Chameleon `.pt` templates
from disk, with standard fallback to an integrated HTML5 layout.
"""

from pathlib import Path
from chameleon import PageTemplate
from golem.config import GolemConfig

DEFAULT_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${title}</title>
    <style>
        :root {
            --golem-bg: #121214;
            --golem-fg: #e2e8f0;
            --golem-primary: #818cf8;
        }
        body {
            background-color: var(--golem-bg);
            color: var(--golem-fg);
            font-family: system-ui, sans-serif;
            display: flex;
            margin: 0;
        }
        #golem-sidebar {
            width: 250px;
            background: #1e1e24;
            padding: 20px;
            height: 100vh;
        }
        #golem-content {
            flex: 1;
            padding: 40px;
        }
        #golem-toc {
            width: 200px;
            padding: 20px;
        }
    </style>
</head>
<body>
    <aside id="golem-sidebar">
        <h3>Documentation</h3>
    </aside>
    <main id="golem-content">
        <h1>${title}</h1>
        <div tal:content="structure body_content" />
    </main>
    <aside id="golem-toc" class="golem-toc">
        <h4>On This Page</h4>
        <div tal:content="structure toc_html" />
    </aside>
</body>
</html>
"""


class PageCompiler:
    """
    = PageCompiler

    Compiles body fragments into complete HTML pages using Chameleon templates.

    === Examples

    [source,python]
    ----
    >>> from golem.config import GolemConfig
    >>> from golem.templates import PageCompiler
    >>> config = GolemConfig(output_dir="dist")
    >>> compiler = PageCompiler(config)
    >>> html = compiler.compile_page("Sample Page", "<p>Paragraph content</p>", "")
    >>> "<title>Sample Page</title>" in html
    True
    >>> "<p>Paragraph content</p>" in html
    True
    ----
    """

    def __init__(self, config: GolemConfig):
        """
        == __init__

        Initialize the compiler with a Golem configuration.
        """
        self.config = config
        self.default_template = PageTemplate(DEFAULT_TEMPLATE)

    def compile_page(
        self,
        title: str,
        body_content: str,
        toc_html: str,
        template_path: Path | None = None,
    ) -> str:
        """
        == compile_page

        Compile a full static page.

        === Arguments

        - `title`:: Document title.
        - `body_content`:: Processed HTML body text.
        - `toc_html`:: Rendered Table of Contents HTML.
        - `template_path`:: Optional layout override path.
        """
        if template_path and template_path.exists():
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    template_content = f.read()
                template = PageTemplate(template_content)
            except Exception:
                template = self.default_template
        else:
            # Fallback to configured themes folder override if exists
            theme_dir = Path("themes") / self.config.theme
            skeleton_pt = theme_dir / "skeleton.pt"
            if skeleton_pt.exists():
                try:
                    with open(skeleton_pt, "r", encoding="utf-8") as f:
                        template_content = f.read()
                    template = PageTemplate(template_content)
                except Exception:
                    template = self.default_template
            else:
                template = self.default_template

        return template(title=title, body_content=body_content, toc_html=toc_html)
