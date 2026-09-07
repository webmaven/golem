"""
= Template Compilation Tests for Golem

This module contains unit tests for verifying the Chameleon page layout compilation,
rich structured context passing, default built-in package templates, and theme/template overrides.
"""

import os
from pathlib import Path

import pytest
from golem.templates import PageCompiler
from golem.config import GolemConfig
import golem


def test_page_layout_compilation(tmp_path):
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Quick Start",
        body_html="<p>Standard paragraph</p>",
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
        <div id="custom-body" tal:content="structure body_html">Body goes here</div>
    </body>
    </html>
    """,
        encoding="utf-8",
    )

    html = compiler.compile_page(
        title="Custom Page",
        body_html="<p>Custom Body Paragraph</p>",
        toc_html="",
        template_path=custom_template_path,
    )
    assert "Custom Template Header" in html
    assert "Custom Body Paragraph" in html
    assert "<title>" not in html  # Ensures it used the disk template, not default


def test_custom_disk_template_fallback_on_invalid_file(tmp_path):
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    # Missing template file path raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        compiler.compile_page(
            title="Fallback Page",
            body_html="<p>Standard Body</p>",
            toc_html="",
            template_path=tmp_path / "non_existent.pt",
        )

    # Corrupt custom template syntax raises template compilation error
    corrupt_tpl = tmp_path / "corrupt_skeleton.pt"
    corrupt_tpl.write_text('<div tal:content="a b c"></div>', encoding="utf-8")
    with pytest.raises(Exception):
        compiler.compile_page(
            title="Corrupt Page",
            body_html="<p>Standard Body</p>",
            toc_html="",
            template_path=corrupt_tpl,
        )


def test_custom_user_defined_page_pt_layout(tmp_path):
    # Scaffold custom templates folder and custom page.pt
    custom_tpl_dir = tmp_path / "custom_templates"
    custom_tpl_dir.mkdir()
    (custom_tpl_dir / "page.pt").write_text(
        """\
<html>
<body>
    <h1>Custom Template: ${title}</h1>
    <div tal:content="structure body_html" />
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
    <title>${title} - ${site_title}</title>
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
        title="Architecture Overview",
        body_html="<article>Deep architectural content</article>",
        toc_html='<ul class="toc"><li>Overview</li></ul>',
        nav_html='<ul class="nav"><li>Link</li></ul>',
        nav_tree=nav_tree,
        current_path="arch/overview.adoc",
        template_path=custom_tpl,
    )

    assert "<title>Architecture Overview - My Docs Site</title>" in html
    assert f'content="{getattr(golem, "__version__", "0.1.0a2")}"' in html
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
        body_html="<p>Welcome to the quickstart guide.</p>",
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
        body_html="<p>Styled text</p>",
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
    <div id="theme-content" tal:content="structure body_html" />
</body>
</html>
""",
        encoding="utf-8",
    )

    config = GolemConfig(theme="modern")
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Theme Page",
        body_html="<p>Theme Content</p>",
        toc_html="",
    )

    assert "<title>Theme Skeleton: Theme Page</title>" in html
    assert '<div id="theme-content"><p>Theme Content</p></div>' in html


def test_chapter_pagination_rendering(tmp_path):
    """Test prev/next chapter pagination cards rendering."""
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Chapter 2: Architecture",
        body_html="<p>Detailed architecture description.</p>",
        toc_html="",
        prev_page={"title": "Introduction", "url": "intro.html"},
        next_page={"title": "Configuration Reference", "url": "config.html"},
    )

    assert 'class="golem-pagination"' in html
    assert 'class="golem-pagination-card golem-pagination-prev"' in html
    assert 'class="golem-pagination-card golem-pagination-next"' in html
    assert 'href="intro.html"' in html
    assert "Introduction" in html
    assert 'href="config.html"' in html
    assert "Configuration Reference" in html
    assert "← Previous" in html
    assert "Next →" in html


def test_compile_page_body_class_and_content_class_default_skeleton(tmp_path):
    """Test body_class and content_class rendering in default skeleton."""
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    # 1. Custom body_class and content_class
    html = compiler.compile_page(
        title="Landing Page",
        body_html="<p>Welcome</p>",
        body_class="landing-page custom-theme",
        content_class="wide-container full-bleed",
    )
    assert '<body class="landing-page custom-theme">' in html
    assert '<main id="golem-content" class="golem-content wide-container full-bleed">' in html

    # 2. Canonical body_class populates body element
    html_page_class = compiler.compile_page(
        title="Doc Page",
        body_html="<p>Doc content</p>",
        body_class="docs-layout",
    )
    assert '<body class="docs-layout">' in html_page_class
    assert '<main id="golem-content" class="golem-content">' in html_page_class

    # 3. Default empty classes should produce clean body tag without class attribute
    html_default = compiler.compile_page(
        title="Standard Page",
        body_html="<p>Standard content</p>",
    )
    assert "<body>" in html_default
    assert '<body class=""' not in html_default
    assert '<body class="None"' not in html_default
    assert '<main id="golem-content" class="golem-content">' in html_default


def test_rich_structured_context_body_class_and_content_class(tmp_path):
    """Test that body_class and content_class are passed to custom templates."""
    custom_tpl = tmp_path / "custom_layout.pt"
    custom_tpl.write_text(
        """\
<!DOCTYPE html>
<html>
<head><title>${title}</title></head>
<body class="${body_class}">
    <main class="${content_class}">
        <div tal:content="structure body_html" />
    </main>
</body>
</html>
""",
        encoding="utf-8",
    )

    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Context Test",
        body_html="<p>Context check</p>",
        body_class="custom-body",
        content_class="custom-main",
        template_path=custom_tpl,
    )
    assert '<body class="custom-body">' in html
    assert '<main class="custom-main">' in html


def test_compile_page_injects_pygments_css(tmp_path):
    """Test that compile_page includes Pygments CSS rules in compiled HTML."""
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Code Page",
        body_html="<p>Some content</p>",
    )
    assert ".highlight" in html
    assert "@media (prefers-color-scheme: dark)" in html


def test_compile_page_custom_pygments_css(tmp_path):
    """Test that custom pygments_css can be passed to compile_page."""
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Custom Highlighting",
        body_html="<p>Content</p>",
        pygments_css="/* Custom Pygments CSS */ .highlight { color: red; }",
    )
    assert "/* Custom Pygments CSS */" in html
    assert ".highlight { color: red; }" in html


def test_compile_page_includes_client_interaction_script(tmp_path):
    """Test that default skeleton template includes client-side copy and tab scripts with preview fallback."""
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Listing Page",
        body_html="<p>Test</p>",
    )
    assert ".listing-copy-btn" in html
    assert "navigator.clipboard" in html
    assert ".tab-btn" in html
    assert ".tab-input" in html
    assert 'data-tab="preview"' in html or "rendered-preview" in html
    assert 'data-tab="source"' in html


def test_skeleton_copy_button_preview_targeting(tmp_path):
    """Verify skeleton client script scopes copy to active pane and falls back to source pane for preview tab."""
    tpl_path = Path(__file__).parent.parent / "src" / "golem" / "templates" / "default" / "skeleton.pt"
    tpl_content = tpl_path.read_text(encoding="utf-8")
    assert "activePane" in tpl_content
    assert "data-tab" in tpl_content
    assert "rendered-preview" in tpl_content
    assert '.tab-pane[data-tab="source"] pre code' in tpl_content


def test_page_compiler_reuses_cached_skeleton_template(tmp_path):
    """Verify PageCompiler reuses the module-level cached skeleton template across instances."""
    import golem.templates as templates_mod

    config1 = GolemConfig(output_dir=str(tmp_path / "dist1"))
    config2 = GolemConfig(output_dir=str(tmp_path / "dist2"))

    c1 = templates_mod.PageCompiler(config1)
    c2 = templates_mod.PageCompiler(config2)

    # Both compilers should share the exact same template instance
    assert c1._pkg_default_template is not None
    assert c1._pkg_default_template is c2._pkg_default_template
    assert c1.default_template is c2.default_template

    # And _CACHED_SKELETON_TEMPLATE exists at module level
    assert getattr(templates_mod, "_CACHED_SKELETON_TEMPLATE", None) is c1._pkg_default_template


def test_missing_builtin_skeleton_template_raises(monkeypatch, tmp_path):
    """Verify missing skeleton.pt raises FileNotFoundError rather than silently falling back."""
    import golem.templates as templates_mod

    monkeypatch.setattr(templates_mod, "_CACHED_SKELETON_TEMPLATE", None)
    monkeypatch.setattr(templates_mod, "BUILTIN_SKELETON_PATH", tmp_path / "nonexistent" / "skeleton.pt")

    with pytest.raises(FileNotFoundError):
        templates_mod._get_builtin_skeleton_template()

    with pytest.raises(FileNotFoundError):
        templates_mod.PageCompiler(GolemConfig())


def test_corrupt_builtin_skeleton_template_raises(monkeypatch, tmp_path):
    """Verify corrupt skeleton.pt raises template parsing error rather than silently suppressing."""
    import golem.templates as templates_mod

    corrupt_file = tmp_path / "skeleton.pt"
    corrupt_file.write_text('<div tal:content="a b c"></div>', encoding="utf-8")

    monkeypatch.setattr(templates_mod, "_CACHED_SKELETON_TEMPLATE", None)
    monkeypatch.setattr(templates_mod, "BUILTIN_SKELETON_PATH", corrupt_file)

    with pytest.raises(Exception):
        templates_mod._get_builtin_skeleton_template()


def test_legacy_argument_aliases_removed(tmp_path):
    """Verify legacy parameter aliases body_content, page_title, and page_class are rejected."""
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    with pytest.raises(TypeError, match="unexpected keyword argument 'body_content'"):
        compiler.compile_page(title="Test", body_content="<p>Test</p>")

    with pytest.raises(TypeError, match="unexpected keyword argument 'page_title'"):
        compiler.compile_page(page_title="Test", body_html="<p>Test</p>")

    with pytest.raises(TypeError, match="unexpected keyword argument 'page_class'"):
        compiler.compile_page(title="Test", body_html="<p>Test</p>", page_class="my-class")


def test_removed_template_context_aliases_not_present(tmp_path):
    """Verify removed context aliases (page_title, body_content, body, navigation_html, page_class) are not available in template."""
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    for alias in ("page_title", "body_content", "body", "navigation_html", "page_class"):
        tpl = tmp_path / f"test_{alias}.pt"
        tpl.write_text(f"<div>${{{alias}}}</div>", encoding="utf-8")
        with pytest.raises(Exception):
            compiler.compile_page(title="Test Title", body_html="<p>Content</p>", template_path=tpl)


def test_corrupt_custom_user_pt_raises(tmp_path):
    """Verify corrupt page.pt in templates_dir raises template error rather than falling back."""
    custom_tpl_dir = tmp_path / "custom_templates"
    custom_tpl_dir.mkdir()
    (custom_tpl_dir / "page.pt").write_text('<div tal:content="a b c"></div>', encoding="utf-8")

    config = GolemConfig(templates_dir=str(custom_tpl_dir))
    compiler = PageCompiler(config)

    with pytest.raises(Exception):
        compiler.compile_page(title="Test Title", body_html="<p>Main Body</p>", toc_html="")


def test_corrupt_theme_skeleton_pt_raises(tmp_path, monkeypatch):
    """Verify corrupt skeleton.pt in themes/<theme> raises template error rather than falling back."""
    monkeypatch.chdir(tmp_path)
    theme_dir = tmp_path / "themes" / "broken"
    theme_dir.mkdir(parents=True)
    (theme_dir / "skeleton.pt").write_text('<div tal:content="a b c"></div>', encoding="utf-8")

    config = GolemConfig(theme="broken")
    compiler = PageCompiler(config)

    with pytest.raises(Exception):
        compiler.compile_page(title="Test Title", body_html="<p>Main Body</p>", toc_html="")


def test_custom_template_path_caching_and_mtime_invalidation(tmp_path):
    """Verify compiling with a custom template_path reuses PageTemplate until mtime changes."""
    custom_tpl = tmp_path / "custom.pt"
    custom_tpl.write_text(
        '<html><body><h1>V1: ${title}</h1><div tal:content="structure body_html" /></body></html>',
        encoding="utf-8",
    )

    compiler = PageCompiler(GolemConfig())

    # Compile first page
    html1 = compiler.compile_page(title="Page 1", body_html="<p>Body 1</p>", template_path=custom_tpl)
    assert "V1: Page 1" in html1
    assert custom_tpl in compiler._disk_template_cache
    cached_mtime1, tpl_instance1 = compiler._disk_template_cache[custom_tpl]

    # Compile second page - should reuse exact same PageTemplate instance
    html2 = compiler.compile_page(title="Page 2", body_html="<p>Body 2</p>", template_path=custom_tpl)
    assert "V1: Page 2" in html2
    cached_mtime2, tpl_instance2 = compiler._disk_template_cache[custom_tpl]
    assert tpl_instance2 is tpl_instance1
    assert cached_mtime2 == cached_mtime1

    # Modify file and update mtime using os.utime
    new_mtime = custom_tpl.stat().st_mtime + 10.0
    custom_tpl.write_text(
        '<html><body><h1>V2: ${title}</h1><div tal:content="structure body_html" /></body></html>',
        encoding="utf-8",
    )
    os.utime(custom_tpl, (new_mtime, new_mtime))

    # Compile third page - cache must invalidate and reload updated template
    html3 = compiler.compile_page(title="Page 3", body_html="<p>Body 3</p>", template_path=custom_tpl)
    assert "V2: Page 3" in html3
    cached_mtime3, tpl_instance3 = compiler._disk_template_cache[custom_tpl]
    assert tpl_instance3 is not tpl_instance1
    assert cached_mtime3 == new_mtime


def test_theme_skeleton_caching_and_mtime_invalidation(tmp_path, monkeypatch):
    """Verify theme skeleton.pt reuses PageTemplate until mtime changes."""
    monkeypatch.chdir(tmp_path)
    theme_dir = tmp_path / "themes" / "customtheme"
    theme_dir.mkdir(parents=True)
    skeleton_pt = theme_dir / "skeleton.pt"
    skeleton_pt.write_text(
        '<html><body><header>Theme V1</header><div tal:content="structure body_html" /></body></html>',
        encoding="utf-8",
    )

    compiler = PageCompiler(GolemConfig(theme="customtheme"))

    # Compile first page
    html1 = compiler.compile_page(title="Page 1", body_html="<p>Body 1</p>")
    assert "<header>Theme V1</header>" in html1

    disk_key = Path("themes") / "customtheme" / "skeleton.pt"
    assert disk_key in compiler._disk_template_cache
    cached_mtime1, tpl_instance1 = compiler._disk_template_cache[disk_key]

    # Compile second page - should reuse cached template
    html2 = compiler.compile_page(title="Page 2", body_html="<p>Body 2</p>")
    assert "<header>Theme V1</header>" in html2
    assert compiler._disk_template_cache[disk_key][1] is tpl_instance1

    # Invalidate via os.utime
    new_mtime = skeleton_pt.stat().st_mtime + 10.0
    skeleton_pt.write_text(
        '<html><body><header>Theme V2</header><div tal:content="structure body_html" /></body></html>',
        encoding="utf-8",
    )
    os.utime(skeleton_pt, (new_mtime, new_mtime))

    # Compile third page - cache invalidates
    html3 = compiler.compile_page(title="Page 3", body_html="<p>Body 3</p>")
    assert "<header>Theme V2</header>" in html3
    cached_mtime3, tpl_instance3 = compiler._disk_template_cache[disk_key]
    assert tpl_instance3 is not tpl_instance1
    assert cached_mtime3 == new_mtime


def test_user_templates_dir_page_pt_caching_and_mtime_invalidation(tmp_path):
    """Verify templates_dir/page.pt reuses PageTemplate until mtime changes."""
    custom_tpl_dir = tmp_path / "custom_templates"
    custom_tpl_dir.mkdir()
    user_pt = custom_tpl_dir / "page.pt"
    user_pt.write_text(
        '<html><body><h1>User V1: ${title}</h1><div tal:content="structure body_html" /></body></html>',
        encoding="utf-8",
    )

    compiler = PageCompiler(GolemConfig(templates_dir=str(custom_tpl_dir)))

    # Compile first page
    html1 = compiler.compile_page(title="Page 1", body_html="<p>Body 1</p>")
    assert "User V1: Page 1" in html1
    assert user_pt in compiler._disk_template_cache
    cached_mtime1, tpl_instance1 = compiler._disk_template_cache[user_pt]

    # Compile second page - reuses template
    html2 = compiler.compile_page(title="Page 2", body_html="<p>Body 2</p>")
    assert "User V1: Page 2" in html2
    assert compiler._disk_template_cache[user_pt][1] is tpl_instance1

    # Invalidate via os.utime
    new_mtime = user_pt.stat().st_mtime + 10.0
    user_pt.write_text(
        '<html><body><h1>User V2: ${title}</h1><div tal:content="structure body_html" /></body></html>',
        encoding="utf-8",
    )
    os.utime(user_pt, (new_mtime, new_mtime))

    # Compile third page
    html3 = compiler.compile_page(title="Page 3", body_html="<p>Body 3</p>")
    assert "User V2: Page 3" in html3
    cached_mtime3, tpl_instance3 = compiler._disk_template_cache[user_pt]
    assert tpl_instance3 is not tpl_instance1
    assert cached_mtime3 == new_mtime
