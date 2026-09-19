from golem.config import GolemConfig
from golem.templates import BUILTIN_SKELETON_PATH, PageCompiler


def test_skeleton_has_metal_slots():
    content = BUILTIN_SKELETON_PATH.read_text(encoding="utf-8")
    assert 'metal:define-macro="layout"' in content
    assert 'metal:define-slot="head"' in content
    assert 'metal:define-slot="header"' in content
    assert 'metal:define-slot="navigation"' in content
    assert 'metal:define-slot="content"' in content
    assert 'metal:define-slot="table-of-contents"' in content
    assert 'metal:define-slot="footer"' in content
    assert '<link rel="stylesheet"' in content
    assert "golem.css" in content


def test_metal_macro_override(tmp_path):
    child_template = tmp_path / "child.pt"
    child_template.write_text(
        """\
<html metal:use-macro="default_layout">
    <div metal:fill-slot="header">
        <header id="custom-header">Overridden Header</header>
    </div>
</html>
""",
        encoding="utf-8",
    )

    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)
    html = compiler.compile_page(
        title="Slot Test",
        body_html="<p>Body</p>",
        template_path=child_template,
    )
    assert '<header id="custom-header">Overridden Header</header>' in html
    assert '<main id="golem-content"' in html


def test_sync_static_assets_copies_golem_css(tmp_path):
    from golem.assets import sync_static_assets

    content_dir = tmp_path / "content"
    content_dir.mkdir()
    output_dir = tmp_path / "dist"
    config = GolemConfig(output_dir=str(output_dir))

    sync_static_assets(config, content_dir, output_dir)

    golem_css = output_dir / "static" / "css" / "golem.css"
    assert golem_css.exists()
    assert ":root" in golem_css.read_text(encoding="utf-8")
