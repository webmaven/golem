"""
= Template Compilation Tests for Golem

This module contains unit tests for verifying the Chameleon page layout compilation,
rich structured context passing, default built-in package templates, and theme/template overrides.
"""

from golem.templates import PageCompiler
from golem.config import GolemConfig
import golem


def test_page_layout_compilation(tmp_path):
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Quick Start",
        body_content="<p>Standard paragraph</p>",
        toc_html="<ul><li>Introduction</li></ul>",
    )
    assert "Quick Start" in html
    assert "Standard paragraph" in html
    assert "golem-toc" in html


def test_custom_disk_template_compilation(tmp_path):
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    custom_template_path = tmp_path / "custom_skeleton.pt"
    custom_template_path.write_text(
        """\
    <html>
    <body>
        <h1>Custom Template Header</h1>
        <div id="custom-body" tal:content="structure body_content">Body goes here</div>
    </body>
    </html>
    """,
        encoding="utf-8",
    )

    html = compiler.compile_page(
        title="Custom Page",
        body_content="<p>Custom Body Paragraph</p>",
        toc_html="",
        template_path=custom_template_path,
    )
    assert "Custom Template Header" in html
    assert "Custom Body Paragraph" in html
    assert "<title>" not in html  # Ensures it used the disk template, not default


def test_custom_disk_template_fallback_on_invalid_file(tmp_path):
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    # Missing file path
    html = compiler.compile_page(
        title="Fallback Page",
        body_content="<p>Standard Body</p>",
        toc_html="",
        template_path=tmp_path / "non_existent.pt",
    )
    assert "Standard Body" in html
    assert "Fallback Page" in html


def test_custom_user_defined_page_pt_layout(tmp_path):
    # Scaffold custom templates folder and custom page.pt
    custom_tpl_dir = tmp_path / "custom_templates"
    custom_tpl_dir.mkdir()
    (custom_tpl_dir / "page.pt").write_text(
        """\
<html>
<body>
    <h1>Custom Template: ${title}</h1>
    <div tal:content="structure body_content" />
</body>
</html>
""",
        encoding="utf-8",
    )

    config = GolemConfig(templates_dir=str(custom_tpl_dir))
    compiler = PageCompiler(config)

    # Compile
    html = compiler.compile_page("Test Title", "<p>Main Body</p>", "")
    assert "Custom Template: Test Title" in html
    assert "<p>Main Body</p>" in html


def test_rich_structured_context_passed_to_template(tmp_path):
    """Test that all required structured context variables are available inside templates."""
    custom_tpl = tmp_path / "custom_context.pt"
    custom_tpl.write_text(
        """\
<!DOCTYPE html>
<html>
<head>
    <title>${page_title} - ${site_title}</title>
    <meta name="generator" content="${generator_version}" />
</head>
<body>
    <span id="author">${site_author}</span>
    <span id="url">${site_url}</span>
    <span id="current-path">${current_path}</span>
    <nav id="nav-html" tal:content="structure nav_html"></nav>
    <aside id="toc-html" tal:content="structure toc_html"></aside>
    <main id="body-html" tal:content="structure body_html"></main>
    <ul id="nav-tree">
        <li tal:repeat="item nav_tree">${item.title} -> ${item.url}</li>
    </ul>
</body>
</html>
""",
        encoding="utf-8",
    )

    config = GolemConfig(
        site_title="My Docs Site",
        site_author="Jane Developer",
        site_url="https://example.com/docs",
    )
    compiler = PageCompiler(config)

    nav_tree = [
        {
            "title": "Introduction",
            "path": "intro.adoc",
            "url": "intro.html",
            "children": [],
        },
        {"title": "Guide", "path": "guide.adoc", "url": "guide.html", "children": []},
    ]

    html = compiler.compile_page(
        page_title="Architecture Overview",
        body_html="<article>Deep architectural content</article>",
        toc_html='<ul class="toc"><li>Overview</li></ul>',
        nav_html='<ul class="nav"><li>Link</li></ul>',
        nav_tree=nav_tree,
        current_path="arch/overview.adoc",
        template_path=custom_tpl,
    )

    assert "<title>Architecture Overview - My Docs Site</title>" in html
    assert f'content="{getattr(golem, "__version__", "0.1.0a1")}"' in html
    assert '<span id="author">Jane Developer</span>' in html
    assert '<span id="url">https://example.com/docs</span>' in html
    assert '<span id="current-path">arch/overview.adoc</span>' in html
    assert '<nav id="nav-html"><ul class="nav"><li>Link</li></ul></nav>' in html
    assert '<aside id="toc-html"><ul class="toc"><li>Overview</li></ul></aside>' in html
    assert '<main id="body-html"><article>Deep architectural content</article></main>' in html
    assert "Introduction -&gt; intro.html" in html or "Introduction -> intro.html" in html
    assert "Guide -&gt; guide.html" in html or "Guide -> guide.html" in html


def test_builtin_default_skeleton_template(tmp_path):
    """Test modern semantic markup rendered by the built-in package skeleton template."""
    config = GolemConfig(
        site_title="Golem Technical Docs",
        site_author="Michael Bernstein",
        site_url="https://webmaven.github.io/golem/",
    )
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Getting Started",
        body_content="<p>Welcome to the quickstart guide.</p>",
        toc_html='<ul class="toc-list"><li><a href="#install">Install</a></li></ul>',
        nav_html='<ul class="golem-nav-list"><li><a href="index.html">Home</a></li></ul>',
        current_path="getting_started.adoc",
    )

    # Modern semantic HTML structure
    assert "<!DOCTYPE html>" in html
    assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in html
    assert "<header" in html and 'id="golem-header"' in html
    assert 'class="golem-header"' in html or 'id="golem-header"' in html
    assert '<aside id="golem-sidebar-left"' in html or 'class="golem-sidebar-left"' in html
    assert '<main id="golem-content"' in html or 'class="golem-content"' in html
    assert '<aside id="golem-sidebar-right"' in html or 'class="golem-toc"' in html
    assert "<footer" in html and 'id="golem-footer"' in html

    # Content verification
    assert "Getting Started" in html
    assert "Welcome to the quickstart guide." in html
    assert "Golem Technical Docs" in html
    assert "Michael Bernstein" in html
    assert "https://webmaven.github.io/golem/" in html
    assert 'href="#install">Install</a>' in html
    assert 'href="index.html">Home</a>' in html


def test_custom_css_and_js_injection(tmp_path):
    """Test custom CSS/JS assets injection into rendered pages."""
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Styled Page",
        body_content="<p>Styled text</p>",
        toc_html="",
        custom_css=["/static/css/theme-dark.css", "/static/css/custom.css"],
        custom_js=["/static/js/search.js", "/static/js/telemetry.js"],
    )

    assert '<link rel="stylesheet" href="/static/css/theme-dark.css"' in html
    assert '<link rel="stylesheet" href="/static/css/custom.css"' in html
    assert '<script src="/static/js/search.js"' in html
    assert '<script src="/static/js/telemetry.js"' in html


def test_workspace_theme_skeleton_override(tmp_path, monkeypatch):
    """Test themes/<theme>/skeleton.pt workspace override resolution."""
    monkeypatch.chdir(tmp_path)

    theme_dir = tmp_path / "themes" / "modern"
    theme_dir.mkdir(parents=True)
    (theme_dir / "skeleton.pt").write_text(
        """\
<!DOCTYPE html>
<html>
<head><title>Theme Skeleton: ${title}</title></head>
<body>
    <div id="theme-content" tal:content="structure body_content" />
</body>
</html>
""",
        encoding="utf-8",
    )

    config = GolemConfig(theme="modern")
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Theme Page",
        body_content="<p>Theme Content</p>",
        toc_html="",
    )

    assert "<title>Theme Skeleton: Theme Page</title>" in html
    assert '<div id="theme-content"><p>Theme Content</p></div>' in html
