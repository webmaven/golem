"""
= Template Compilation Tests for Golem

This module contains unit tests for verifying the Chameleon page layout compilation and theme override/fallback behaviors.
"""

import pytest
from pathlib import Path
from golem.templates import PageCompiler
from golem.config import GolemConfig


def test_page_layout_compilation(tmp_path):
    config = GolemConfig(output_dir=str(tmp_path / "dist"))
    compiler = PageCompiler(config)

    html = compiler.compile_page(
        title="Quick Start",
        body_content="<p>Standard paragraph</p>",
        toc_html="<ul><li>Introduction</li></ul>",
    )
    assert "<title>Quick Start</title>" in html
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
    assert (
        "<title>Fallback Page</title>" in html
    )  # Confirms fallback to DEFAULT_TEMPLATE
