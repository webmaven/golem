# tests/test_templates.py
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
        toc_html="<ul><li>Introduction</li></ul>"
    )
    assert "<title>Quick Start</title>" in html
    assert "Standard paragraph" in html
    assert "golem-toc" in html
