from __future__ import annotations

import re

import click
from click.testing import CliRunner

from golem.config import GolemConfig
from golem.engine import BuildEngine
from golem.plugins import get_plugin_manager


def test_apidoc_plugin_registration():
    from golem.plugins import apidoc

    pm = get_plugin_manager()
    pm.register(apidoc)
    assert pm.is_registered(apidoc)


def test_ast_level_apidoc_splicing_with_typed_nodes(tmp_path):
    from asciidoctrine import parse_to_ast
    from asciidoctrine.resolver import ASGResolver
    from golem.model import Node
    from golem.plugins import apidoc
    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "typed_test_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Sample package for typed ASG splicing."""
class Greeter:
    """Greeter class."""
    def greet(self, name: str) -> str:
        """Return a greeting."""
        return f"Hello, {name}!"
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        # 1. Verify get_asg_nodes returns typed Node list
        api = AsciiDocApi(search_paths=[tmp_path])
        nodes = api.get_asg_nodes("typed_test_pkg.Greeter")
        assert len(nodes) > 0
        assert all(isinstance(n, Node) for n in nodes)

        # 2. Verify on_asg_created splices typed Nodes into ASG
        raw_doc = """= Typed Splice Test

Introductory text.

golem.apidoc::typed_test_pkg.Greeter[depth=all]

Concluding text.
"""
        ast = parse_to_ast(raw_doc)
        asg = ASGResolver(ast).resolve_to_ast(ast)
        transformed = apidoc.on_asg_created(asg=asg)
        assert isinstance(transformed, Node)

        # Verify no golem.apidoc block remains and section is spliced
        block_names = [b.name for b in transformed.blocks]
        assert "golem.apidoc" not in block_names
        assert "section" in block_names

        # Verify rendered output
        html = render_body(transformed)
        assert "Greeter" in html
        assert "greet" in html
        assert "Return a greeting." in html
        assert "Introductory text." in html
        assert "Concluding text." in html
    finally:
        sys.path.remove(str(tmp_path))


def test_get_asg_nodes_invalid_symbol_returns_typed_admonition():
    from asciidoctrine.nodes import Admonition
    from golem.model import Node
    from golem.plugins.apidoc import AsciiDocApi

    api = AsciiDocApi()
    nodes = api.get_asg_nodes("completely_nonexistent_module_999.Fake")
    assert len(nodes) == 1
    assert isinstance(nodes[0], Node)
    assert isinstance(nodes[0], Admonition)
    assert nodes[0].name == "admonition"
    assert nodes[0].variant == "warning"
    assert "Could not resolve target" in str(nodes[0].blocks[0].inlines[0].value)


def test_get_asg_nodes_does_not_parse_generated_symbol_markup(tmp_path, monkeypatch):
    import sys

    from golem.plugins.apidoc import AsciiDocApi

    pkg_dir = tmp_path / "direct_asg_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("def square(value: int) -> int:\n    return value * value\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:

        def unexpected_parse(_source):
            raise AssertionError("generated symbol markup should not be parsed")

        monkeypatch.setattr("golem.plugins.apidoc.core.api.asciidoctrine.parse_to_ast", unexpected_parse)
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("direct_asg_pkg.square")

        assert nodes
        assert nodes[0].name == "section"
    finally:
        sys.path.remove(str(tmp_path))


def test_get_asg_nodes_includes_nested_classes(tmp_path):
    import sys

    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "nested_class_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        "class Outer:\n    class Inner:\n        pass\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("nested_class_pkg.Outer")
        html = render_body(nodes[0])

        assert "Outer" in html
        assert "Inner" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_get_asg_nodes_class_attribute_with_docstring_retains_default_value(tmp_path):
    import sys

    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "attr_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        "class Config:\n    port: int = 8080\n    '''Port number configuration.'''\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("attr_pkg.Config")
        html = render_body(nodes[0])

        assert "port" in html
        assert "Port number configuration." in html
        assert "8080" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_get_asg_nodes_resolves_aliased_members(tmp_path):
    import sys

    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "alias_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "mod.py").write_text("def helper():\n    '''A helper.'''\n    pass\n", encoding="utf-8")
    (pkg_dir / "__init__.py").write_text("from .mod import helper\n", encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("alias_pkg")
        assert len(nodes) > 0
        html = "\n".join(render_body(n) for n in nodes)
        assert "helper" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_source_drawer_rendered_under_functions(tmp_path):
    """#24: every function/method carries a collapsed-by-default source drawer."""
    import sys

    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "drawer_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '"""Drawer fixture."""\n\n\ndef start() -> None:\n    """Start it."""\n    return None\n',
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("drawer_pkg")
        html = "\n".join(render_body(n) for n in nodes)

        assert '<details class="source-drawer">' in html, "Missing source drawer (#24)"
        assert "<summary>View source</summary>" in html, "Missing 'View source' summary (#24)"
        assert '<pre class="highlight python">' in html, "Drawer must contain a highlighted Python listing (#24)"
        assert '<span class="k">def</span>' in html, "Drawer source must carry Pygments token spans (#24)"
        assert '<span class="nf">start</span>' in html, "Drawer source must contain the function name (#24)"

        # The drawer is the LAST block of the member section: after the docstring.
        drawer_idx = html.find('<details class="source-drawer">')
        doc_idx = html.find("<p>Start it.</p>")
        assert doc_idx != -1 and doc_idx < drawer_idx, "Source drawer must follow the docstring (#24)"
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_source_drawer_omitted_without_source():
    """#24: no drawer is emitted when there is no source to show."""
    from golem.plugins.apidoc import AsciiDocApi

    class _NoSource:
        source = None

    class _BlankSource:
        source = "   \n  "

    assert AsciiDocApi._source_drawer(_NoSource()) is None, "None source must yield no drawer (#24)"
    assert AsciiDocApi._source_drawer(_BlankSource()) is None, "Blank source must yield no drawer (#24)"


def test_glyph_classification_all_kinds(tmp_path):
    """#19: every symbol kind maps to its dual-coding glyph badge.

    The fixture deliberately decorates with an *aliased* import (@dataclass from
    dataclasses) to prove classification never depends on Griffe's aliases —
    `.labels`/`.decorators` raise for those, so the mapping must not need them.
    """
    import sys

    from golem.plugins.apidoc import AsciiDocApi

    pkg_dir = tmp_path / "glyph_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Glyph fixture."""
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Point:
    """A point."""
    x: int = 0


class Shape(Protocol):
    """A shape."""
    def area(self) -> float: ...


class ConfigError(Exception):
    """Config failure."""


class Engine:
    """An engine."""
    def start(self) -> None:
        """Start it."""


async def fetch(url: str) -> bytes:
    """Fetch bytes."""
    return b""


MAX_SIZE = 10
''',
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        api = AsciiDocApi(search_paths=[tmp_path])
        pkg = api.load_package("glyph_pkg")

        point = pkg.members["Point"]
        assert api._symbol_glyph(point) == {"letter": "T", "css_class": "glyph-type", "label": "Type"}

        shape = pkg.members["Shape"]
        assert api._symbol_glyph(shape) == {"letter": "I", "css_class": "glyph-interface", "label": "Interface"}

        error = pkg.members["ConfigError"]
        assert api._symbol_glyph(error) == {"letter": "X", "css_class": "glyph-exception", "label": "Exception"}

        engine = pkg.members["Engine"]
        assert api._symbol_glyph(engine) == {"letter": "C", "css_class": "glyph-class", "label": "Class"}
        start = engine.members["start"]
        assert api._symbol_glyph(start, is_member=True) == {"letter": "M", "css_class": "glyph-method", "label": "Method"}

        fetch_fn = pkg.members["fetch"]
        assert api._symbol_glyph(fetch_fn) == {"letter": "F", "css_class": "glyph-function", "label": "Function"}

        attr = pkg.members["MAX_SIZE"]
        assert api._symbol_glyph(attr) == {"letter": "V", "css_class": "glyph-constant", "label": "Variable"}
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_glyph_badges_render_in_headings(tmp_path):
    """#19: glyph badges render in a .doc-title-row before the member heading."""
    import sys

    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "glyph_render_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '"""Glyph render fixture."""\n\n\nclass Engine:\n    """An engine."""\n\n    def start(self) -> None:\n        """Start it."""\n\n\nMAX_SIZE = 10\n',
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("glyph_render_pkg", depth="all")
        html = "\n".join(render_body(n) for n in nodes)

        assert (
            '<div class="doc-title-row"><h2><span class="symbol-glyph glyph-class" aria-label="Class">C</span>class Engine</h2></div>'
            in html
        ), "Class glyph must lead the heading inside .doc-title-row (#19)"
        assert (
            '<div class="doc-title-row"><h3><span class="symbol-glyph glyph-method" aria-label="Method">M</span>start</h3></div>'
            in html
        ), "Method glyph must lead the heading inside .doc-title-row (#19)"
        assert (
            '<div class="doc-title-row"><h2><span class="symbol-glyph glyph-constant" aria-label="Variable">V</span>MAX_SIZE</h2></div>'
            in html
        ), "Variable glyph must lead the heading inside .doc-title-row (#19)"
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


PILL_FIXTURE = '''"""Pill fixture."""
from abc import abstractmethod


async def fetch(url: str) -> bytes:
    """Fetch bytes."""
    return b""


def documented(x: int) -> int:
    """Documented.

    :versionadded: 0.4

    Body.
    """
    return x


def legacy(x: int) -> int:
    """Legacy.

    [deprecated]
    Use modern() instead.
    """
    return x


def maybe(x: int) -> int:
    """Maybe.

    :experimental:

    Body.
    """
    return x


def plain(x: int) -> int:
    """Plain."""
    return x


class Svc:
    """A service."""

    def __init__(self) -> None:
        """Build it."""

    @classmethod
    def make(cls) -> "Svc":
        """Make one."""

    @staticmethod
    def util() -> None:
        """Utility."""

    @abstractmethod
    def run(self) -> None:
        """Run it."""
'''


def _load_pill_pkg(tmp_path):
    import sys

    from golem.plugins.apidoc import AsciiDocApi

    pkg_dir = tmp_path / "pill_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(PILL_FIXTURE, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        return AsciiDocApi(search_paths=[tmp_path]), AsciiDocApi(search_paths=[tmp_path]).load_package("pill_pkg")
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_modifier_pill_detection(tmp_path):
    """#20: runtime + docstring semantic pills are detected per condition."""
    api, pkg = _load_pill_pkg(tmp_path)

    def pills(name, is_member=False):
        obj = pkg.members[name]
        parsed = api._parse_docstring(api._raw_docstring(obj.docstring))
        return api._member_pills(obj, is_member=is_member, parsed=parsed)

    assert pills("fetch") == [{"text": "Async", "css_class": "pill-async", "title": None}]

    assert pills("documented") == [{"text": "Stable v0.4+", "css_class": "pill-baseline", "title": None}]

    legacy = pills("legacy")
    assert legacy == [{"text": "Deprecated", "css_class": "pill-deprecated", "title": "Use modern() instead."}], legacy

    assert pills("maybe") == [{"text": "Experimental", "css_class": "pill-experimental", "title": None}]

    assert pills("plain") == []

    svc = pkg.members["Svc"]

    def method_pills(name):
        obj = svc.members[name]
        parsed = api._parse_docstring(api._raw_docstring(obj.docstring))
        return api._member_pills(obj, is_member=True, parsed=parsed)

    assert method_pills("__init__") == [{"text": "Constructor", "css_class": "pill-runtime", "title": None}]
    assert method_pills("make") == [{"text": "classmethod", "css_class": "pill-runtime", "title": None}]
    assert method_pills("util") == [{"text": "staticmethod", "css_class": "pill-runtime", "title": None}]
    assert method_pills("run") == [{"text": "abstract", "css_class": "pill-runtime", "title": None}]


def test_modifier_pills_render_after_heading(tmp_path):
    """#20: pills render inside the .doc-title-row, after the heading."""
    import sys

    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "pill_render_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(PILL_FIXTURE, encoding="utf-8")
    sys.path.insert(0, str(tmp_path))
    try:
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("pill_render_pkg", depth="all")
        html = "\n".join(render_body(n) for n in nodes)

        assert (
            '<h2><span class="symbol-glyph glyph-function" aria-label="Function">F</span>fetch</h2><span class="pill pill-async">Async</span></div>'
            in html
        ), "Async pill must render right after the heading (#20)"
        assert (
            '<h2><span class="symbol-glyph glyph-function" aria-label="Function">F</span>documented</h2><span class="pill pill-baseline">Stable v0.4+</span></div>'
            in html
        ), "Baseline pill must render with the version string (#20)"
        assert (
            '<h2><span class="symbol-glyph glyph-function" aria-label="Function">F</span>legacy</h2><span class="pill pill-deprecated" title="Use modern() instead.">Deprecated</span></div>'
            in html
        ), "Deprecated pill must carry the replacement note as a tooltip (#20)"
        assert (
            '<h2><span class="symbol-glyph glyph-function" aria-label="Function">F</span>maybe</h2><span class="pill pill-experimental">Experimental</span></div>'
            in html
        ), "Experimental pill must render (#20)"
        assert '<h2><span class="symbol-glyph glyph-function" aria-label="Function">F</span>plain</h2></div>' in html, (
            "Plain members must carry no pills (#20)"
        )
        assert (
            '<h3><span class="symbol-glyph glyph-method" aria-label="Method">M</span>make</h3><span class="pill pill-runtime">classmethod</span></div>'
            in html
        ), "Runtime pills must render on methods (#20)"
        assert (
            '<h3><span class="symbol-glyph glyph-method" aria-label="Method">M</span>__init__</h3><span class="pill pill-runtime">Constructor</span></div>'
            in html
        ), "Constructor pill must render (#20)"
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_signature_block_aria_label_and_token_spans(tmp_path):
    """#23: signature blocks are labelled, tokenised, and scrollable.

    Acceptance: syntax-highlighted parameter/return tokens (ast-token spans),
    monospace typography + overflow-x scroll in .signature-container CSS, and an
    aria-label so screen readers announce the block as a method signature.
    """
    import sys

    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "sig_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        "def send(url: str, retries: int = 3) -> bool:\n    '''Send the payload.'''\n    return True\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("sig_pkg.send")
        html = "\n".join(render_body(n) for n in nodes)
        assert 'class="signature-container' in html, "Missing .signature-container (#23)"
        assert 'aria-label="Method signature"' in html, "Missing aria-label on .signature-container (#23)"
        assert '<span class="ast-token">' in html, "Missing tokenised annotation spans (#23)"
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_apidoc_template_directory_registered():
    from pathlib import Path
    import asciidoctype
    import golem.plugins.apidoc

    registered = asciidoctype.AsciiDoctypeRenderer.get_registered_template_directories()
    apidoc_tpl_dir = Path(golem.plugins.apidoc.__file__).parent / "templates" / "html5"
    assert apidoc_tpl_dir.resolve() in [p.resolve() for p in registered]


def test_apidoc_renders_member_card_and_class_multi_grid(tmp_path):
    import sys

    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "card_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        "class Worker:\n"
        "    '''A worker service.'''\n"
        "    def run(self, count: int = 1) -> bool:\n"
        "        '''Run the worker process.\n"
        "\n"
        "        Examples:\n"
        "            >>> w = Worker()\n"
        "            >>> w.run()\n"
        "            True\n"
        "        '''\n"
        "        return True\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        nodes = AsciiDocApi(search_paths=[tmp_path]).get_asg_nodes("card_pkg.Worker")
        html = render_body(nodes[0])

        assert "class-multi-grid" in html
        assert "member-card" in html
        assert "ast-token" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_macro_replacement(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    # Create a target package to document
    pkg_dir = tmp_path / "calc_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Calculator module."""
def multiply(x: int, y: int) -> int:
    """Multiply two numbers.

    Args:
        x: First factor.
        y: Second factor.

    Returns:
        Product of x and y.
    """
    return x * y
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Arithmetic Guide

Here is our multiply function:

golem.apidoc::calc_pkg.multiply[]

And more content.
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        resolver = ASGResolver(ast)
        asg = resolver.resolve_to_ast(ast)

        # Apply on_asg_created hook
        asg = apidoc.on_asg_created(asg=asg)

        # Render HTML from modified ASG
        html = render_body(asg)
        assert "golem.apidoc" not in html
        assert "multiply" in html
        assert "Multiply two numbers." in html
        assert "Here is our multiply function:" in html
        assert "And more content." in html
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_syntax_variants(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    pkg_dir = tmp_path / "syn_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Syntax test pkg."""
def test_fn() -> None:
    """A test function."""
    pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        variants = [
            "golem.apidoc::syn_pkg.test_fn[]",
            'golem.apidoc::"syn_pkg.test_fn"[]',
            "golem.apidoc::syn_pkg.test_fn[depth=summary]",
            "golem.apidoc::syn_pkg.test_fn[style=auto]",
        ]
        for v in variants:
            raw = f"= Page\n\n{v}\n"
            ast = asciidoctrine.parse_to_ast(raw)
            resolver = ASGResolver(ast)
            asg = resolver.resolve_to_ast(ast)

            asg = apidoc.on_asg_created(asg=asg)
            html = render_body(asg)
            assert "golem.apidoc" not in html
            assert "test_fn" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_missing_symbol_graceful():
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    raw = "= Missing Page\n\ngolem.apidoc::nonexistent_pkg_123.fake_func[]\n"
    ast = asciidoctrine.parse_to_ast(raw)
    resolver = ASGResolver(ast)
    asg = resolver.resolve_to_ast(ast)

    asg = apidoc.on_asg_created(asg=asg)
    html = render_body(asg)
    assert "golem.apidoc" not in html
    assert "nonexistent_pkg_123.fake_func" in html
    assert "admonitionblock warning" in html


def test_on_asg_created_preserves_sections_and_surrounding_blocks(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    pkg_dir = tmp_path / "sect_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Section test package."""
class Worker:
    """Worker class docstring."""
    def perform(self) -> None:
        """Perform action."""
        pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Main Document

Initial overview text.

== Section One

Section one intro.

golem.apidoc::sect_pkg.Worker[]

Section one outro.

== Section Two

Section two text.
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        resolver = ASGResolver(ast)
        asg = resolver.resolve_to_ast(ast)

        # Apply on_asg_created
        asg = apidoc.on_asg_created(asg=asg)

        html = render_body(asg)
        assert "Initial overview text." in html
        assert "Section One" in html
        assert "Section one intro." in html
        assert "Worker" in html
        assert "Worker class docstring." in html
        assert "Section one outro." in html
        assert "Section Two" in html
        assert "Section two text." in html

        # Verify ordering of sections and content
        idx_intro = html.index("Section one intro.")
        idx_worker = html.index("Worker class docstring.")
        idx_outro = html.index("Section one outro.")
        idx_sect2 = html.index("Section Two")
        assert idx_intro < idx_worker < idx_outro < idx_sect2
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_heading_offset(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    pkg_dir = tmp_path / "offset_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Offset package."""
def helper() -> None:
    """Helper function."""
    pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Offset Doc

golem.apidoc::offset_pkg.helper[heading_level_offset=1]
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        resolver = ASGResolver(ast)
        asg = resolver.resolve_to_ast(ast)

        asg = apidoc.on_asg_created(asg=asg)
        html = render_body(asg)
        assert "helper" in html
        # With heading_level_offset=1, function renders as h3 instead of h2
        assert "<h3" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_splices_block_macro(monkeypatch):
    import asciidoctrine
    from asciidoctrine.nodes import Paragraph, Section, Text
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc

    fake_nodes = [
        Section(level=2, title=[Text("Fake Module")]),
        Paragraph(inlines=[Text("Doc content")]),
    ]
    monkeypatch.setattr(
        "golem.plugins.apidoc.AsciiDocApi.get_asg_nodes",
        lambda self, target, **kwargs: fake_nodes,
    )

    raw = "= Document\n\ngolem.apidoc::some.pkg[]\n"
    ast = asciidoctrine.parse_to_ast(raw)
    asg = ASGResolver(ast).resolve_to_ast(ast)
    result = apidoc.on_asg_created(asg)
    assert result.blocks == fake_nodes


def test_on_asg_created_preserves_surrounding_blocks(monkeypatch):
    import asciidoctrine
    from asciidoctrine.nodes import Section, Text
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc

    fake_nodes = [Section(level=2, title=[Text("Injected Section")])]
    monkeypatch.setattr(
        "golem.plugins.apidoc.AsciiDocApi.get_asg_nodes",
        lambda self, target, **kwargs: fake_nodes,
    )

    raw = "= Document\n\nBefore\n\ngolem.apidoc::some.pkg[]\n\nAfter\n"
    ast = asciidoctrine.parse_to_ast(raw)
    asg = ASGResolver(ast).resolve_to_ast(ast)
    result = apidoc.on_asg_created(asg)
    assert len(result.blocks) == 3
    assert result.blocks[0].inlines[0].value == "Before"
    assert result.blocks[1] == fake_nodes[0]
    assert result.blocks[2].inlines[0].value == "After"


def test_on_asg_created_noop_without_macros():
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc

    raw = "= Document\n\nHello world\n\n== Section\n\nInner paragraph\n"
    ast = asciidoctrine.parse_to_ast(raw)
    asg = ASGResolver(ast).resolve_to_ast(ast)
    orig_block_count = len(asg.blocks)
    result = apidoc.on_asg_created(asg)
    assert len(result.blocks) == orig_block_count
    assert result.blocks[0].inlines[0].value == "Hello world"


def test_on_asg_created_nested_section_splicing(monkeypatch):
    import asciidoctrine
    from asciidoctrine.nodes import Paragraph, Text
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc

    fake_nodes = [Paragraph(inlines=[Text("Spliced in section")])]
    monkeypatch.setattr(
        "golem.plugins.apidoc.AsciiDocApi.get_asg_nodes",
        lambda self, target, **kwargs: fake_nodes,
    )

    raw = "= Document\n\n== Section Header\n\ngolem.apidoc::nested.pkg[]\n"
    ast = asciidoctrine.parse_to_ast(raw)
    asg = ASGResolver(ast).resolve_to_ast(ast)
    result = apidoc.on_asg_created(asg)
    section = result.blocks[0]
    assert section.name == "section"
    assert len(section.blocks) == 1
    assert section.blocks[0] == fake_nodes[0]


def test_apidoc_cli_subcommand(tmp_path):
    from golem.plugins import apidoc

    pkg_dir = tmp_path / "cli_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""CLI target package."""
def cli_action() -> str:
    """Perform action."""
    return "done"
''',
        encoding="utf-8",
    )

    out_dir = tmp_path / "api_out"

    @click.group()
    def cli():
        pass

    apidoc.golem_add_subcommands(cli)

    runner = CliRunner()
    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        result = runner.invoke(cli, ["apidoc", "cli_pkg", "-o", str(out_dir)])
        assert result.exit_code == 0
        assert out_dir.exists()
        adoc_files = list(out_dir.glob("*.adoc"))
        assert len(adoc_files) >= 1
    finally:
        sys.path.remove(str(tmp_path))


def test_build_engine_integration_with_apidoc(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    dist_dir = tmp_path / "dist"

    doc_text = """= Golem Config Guide

Documentation for configuration:

golem.apidoc::golem.config.GolemConfig[]
"""
    (content_dir / "index.adoc").write_text(doc_text, encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(dist_dir),
        plugins=["golem.plugins.apidoc"],
    )

    engine = BuildEngine(config)
    engine.build_site()

    out_html = (dist_dir / "index.html").read_text(encoding="utf-8")
    assert "Golem Config Guide" in out_html
    assert "GolemConfig" in out_html
    assert "site_title" in out_html


def test_format_attribute_and_module_attributes(tmp_path):
    """Verify format_attribute() and format_module() rendering of module-level attributes."""
    import sys
    from golem.plugins.apidoc.core.extractor import create_griffe_loader, resolve_symbol
    from golem.plugins.apidoc.core.formatter import format_attribute, format_module

    mod_dir = tmp_path / "attrs_pkg"
    mod_dir.mkdir()
    (mod_dir / "__init__.py").write_text(
        '''"""Constants and configuration attributes."""

API_VERSION: str = "2.0.0"
"""Current API version string."""

MAX_RETRIES: int = 5
"""Maximum number of HTTP retries."""

LONG_DESCRIPTION: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
"""A very long constant value."""

UNANNOTATED_VAR = "some_val"

EMPTY_DOC_VAR: float = 3.14

class ServiceConfig:
    """Service configuration class."""
    timeout: int = 30
    """Request timeout in seconds."""
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        loader = create_griffe_loader([tmp_path])
        mod_obj = resolve_symbol(loader, "attrs_pkg")

        # Test format_module() output contains Module Attributes heading and description list
        mod_adoc = format_module(mod_obj, depth="all", heading_level=1)
        assert "= attrs_pkg" in mod_adoc
        assert "== Module Attributes" in mod_adoc
        assert "`API_VERSION`:: (str)" in mod_adoc
        assert "Current API version string." in mod_adoc
        assert 'Default value: `"2.0.0"`' in mod_adoc or "2.0.0" in mod_adoc

        assert "`MAX_RETRIES`:: (int)" in mod_adoc
        assert "Maximum number of HTTP retries." in mod_adoc
        assert "Default value: `5`" in mod_adoc

        assert "`LONG_DESCRIPTION`:: (str)" in mod_adoc
        assert "(truncated; see source)" in mod_adoc

        # Test format_attribute() directly on single attribute
        attr_obj = resolve_symbol(loader, "attrs_pkg.API_VERSION")
        attr_adoc = format_attribute(attr_obj, heading_level=2)
        assert "== API_VERSION" in attr_adoc
        assert '[source,python]\n----\nAPI_VERSION: str = "2.0.0"\n----' in attr_adoc or "API_VERSION: str" in attr_adoc
        assert "Current API version string." in attr_adoc

        # Test format_attribute without annotation
        raw_attr = resolve_symbol(loader, "attrs_pkg.UNANNOTATED_VAR")
        raw_adoc = format_attribute(raw_attr, heading_level=3)
        assert "=== UNANNOTATED_VAR" in raw_adoc
        assert "UNANNOTATED_VAR" in raw_adoc
    finally:
        sys.path.remove(str(tmp_path))


def test_on_asg_created_verbatim_and_backtick_protection():
    """Verify on_asg_created does not expand macros in backticks or verbatim blocks."""
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body

    raw = """= Guide

Here is `golem.apidoc::inline[]` in an inline code span.

[source,asciidoc]
----
= Code Listing
golem.apidoc::some.pkg.Class[depth=all]
----

....
golem.apidoc::literal_block[]
....

And \\golem.apidoc::escaped[] is escaped.
"""
    ast = asciidoctrine.parse_to_ast(raw)
    resolver = ASGResolver(ast)
    asg = resolver.resolve_to_ast(ast)

    asg = apidoc.on_asg_created(asg=asg)
    html = render_body(asg)

    # Inline backticks preserved
    assert "golem.apidoc::inline[]" in html

    # Verbatim blocks preserved without expansion or warnings
    assert "golem.apidoc::some.pkg.Class[depth=all]" in html
    assert "golem.apidoc::literal_block[]" in html

    # Escaped macro unescaped
    assert "golem.apidoc::escaped[]" in html
    assert "\\golem.apidoc" not in html


def test_apidoc_format_composite_types(tmp_path):
    from golem.plugins.apidoc import AsciiDocApi
    import sys

    pkg_dir = tmp_path / "typed_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Typed module."""
from typing import Union, Optional

def process_data(data: Union[dict[str, int], list[str]], timeout: Optional[float] = None) -> dict[str, Any]:
    """Process incoming data payload.

    Args:
        data (dict[str, int] or list[str]): Input payload.
        timeout (float, optional): Optional timeout in seconds. Defaults to 1.0.

    Returns:
        result (dict[str, Any]): Processed result mapping.
    """
    return {}
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        api = AsciiDocApi(search_paths=[tmp_path])
        res = api.render_symbol("typed_pkg.process_data")
        assert "process_data" in res
        assert "data" in res
        assert "timeout" in res

        # Verify signature has composite and optional types
        assert (
            "def process_data(data: Union[dict[str, int], list[str]], timeout: Optional[float] = None) -> dict[str, Any]:"
            in res
        )

        # Verify docstring parameter composite type conversion
        assert "`data`:: (dict[str, int] or list[str]) Input payload." in res
        assert "`timeout`:: (float, optional) Optional timeout in seconds." in res

        # Verify docstring named return value and composite return type
        assert "`result` (dict[str, Any]):: Processed result mapping." in res
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_format_docstring_composite_types_and_named_returns():
    from golem.plugins.apidoc.core.formatter import format_docstring

    doc = """Process incoming data payload.

Args:
    payload (Union[dict[str, int], list[str]]): Input payload data.
    timeout (Optional[float]): Optional timeout in seconds.

Returns:
    result (dict[str, Any]): Processed result mapping.

Yields:
    item (Union[str, int]): Streamed progress item.
"""
    adoc = format_docstring(doc, style="google")
    assert "[parameters]" in adoc
    assert "`payload`:: (Union[dict[str, int], list[str]]) Input payload data." in adoc
    assert "`timeout`:: (Optional[float]) Optional timeout in seconds." in adoc
    assert "[returns]" in adoc
    assert "`result` (dict[str, Any]):: Processed result mapping." in adoc
    assert "[yields]" in adoc
    assert "`item` (Union[str, int]):: Streamed progress item." in adoc


def test_on_asg_created_composite_types(tmp_path):
    import asciidoctrine
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.renderer import render_body
    import sys

    pkg_dir = tmp_path / "asg_typed_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Typed module."""
from typing import Union, Optional

def process_data(data: Union[dict[str, int], list[str]], timeout: Optional[float] = None) -> dict[str, Any]:
    """Process incoming data payload.

    Args:
        data (dict[str, int] or list[str]): Input payload.
        timeout (float, optional): Optional timeout in seconds. Defaults to 1.0.

    Returns:
        result (dict[str, Any]): Processed result mapping.
    """
    return {}
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Typed Guide

golem.apidoc::asg_typed_pkg.process_data[]
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        asg = ASGResolver(ast).resolve_to_ast(ast)
        spliced_asg = apidoc.on_asg_created(asg=asg)
        html = render_body(spliced_asg)
        assert "process_data" in html
        assert "dict[str, int]" in html
        assert "result" in html
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_format_docstring_defensive_fallback():
    from unittest.mock import patch
    import pytest
    from golem.plugins.apidoc.core.formatter import format_docstring

    doc = "Some plain text docstring."
    # If griffe.parse raises an exception, it propagates directly
    with patch("griffe.parse", side_effect=RuntimeError("Parsing error")):
        with pytest.raises(RuntimeError, match="Parsing error"):
            format_docstring(doc)

    # If asciidocstring.griffe_bridge.to_asciidoc raises an exception, it propagates directly
    with patch("asciidocstring.griffe_bridge.to_asciidoc", side_effect=RuntimeError("Bridge error")):
        with pytest.raises(RuntimeError, match="Bridge error"):
            format_docstring(doc)

    # If to_asciidoc returns empty string or whitespace for non-empty docstring, fall back to raw
    with patch("asciidocstring.griffe_bridge.to_asciidoc", return_value=""):
        res = format_docstring(doc)
        assert res == "Some plain text docstring."

    with patch("asciidocstring.griffe_bridge.to_asciidoc", return_value="   \n\t  "):
        res = format_docstring(doc)
        assert res == "Some plain text docstring."


def test_format_docstring_style_variants():
    import griffe
    from golem.plugins.apidoc.core.formatter import format_docstring

    doc = """Process data.

Args:
    x (int): Value.
"""
    # Parser enum
    res1 = format_docstring(doc, style=griffe.Parser.google)
    assert "[parameters]" in res1
    assert "`x`:: (int) Value." in res1

    # Uppercase string
    res2 = format_docstring(doc, style="GOOGLE")
    assert "[parameters]" in res2
    assert "`x`:: (int) Value." in res2


def test_on_build_start_is_registered_hookimpl():
    """Verify on_build_start is defined and registered as a hookimpl in the apidoc plugin."""
    from golem.plugins import apidoc, get_plugin_manager

    assert hasattr(apidoc, "on_build_start")
    pm = get_plugin_manager()
    pm.register(apidoc)
    hookimpls = pm.hook.on_build_start.get_hookimpls()
    apidoc_impls = [h for h in hookimpls if h.plugin is apidoc]
    assert len(apidoc_impls) == 1
    assert apidoc_impls[0].function == apidoc.on_build_start


def test_on_build_start_invokes_generate_api_docs_when_configured(tmp_path, monkeypatch):
    """Verify calling on_build_start with api_packages invokes generate_api_docs with expected args."""
    from pathlib import Path
    from golem.plugins import apidoc

    calls = []

    def mock_generate_api_docs(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(apidoc, "generate_api_docs", mock_generate_api_docs)

    config = GolemConfig(
        content_dir=str(tmp_path / "docs"),
        api_packages=["mypackage", "otherpackage"],
        api_output_dir="reference",
        api_docstring_style="sphinx",
    )

    apidoc.on_build_start(config)

    assert len(calls) == 1
    assert calls[0]["packages"] == ["mypackage", "otherpackage"]
    assert calls[0]["output_dir"] == tmp_path / "docs" / "reference"
    assert calls[0]["docstring_style"] == "sphinx"
    assert any(str(p) == str(Path.cwd()) for p in calls[0]["search_paths"])


def test_on_build_start_noop_when_api_packages_unset_or_empty(tmp_path, monkeypatch):
    """Verify calling on_build_start does nothing if api_packages is None or empty."""
    from golem.plugins import apidoc

    calls = []

    def mock_generate_api_docs(**kwargs):
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(apidoc, "generate_api_docs", mock_generate_api_docs)

    # When empty list
    config_empty = GolemConfig(content_dir=str(tmp_path / "docs"), api_packages=[])
    apidoc.on_build_start(config_empty)
    assert len(calls) == 0

    # When None
    class ConfigNone:
        content_dir = str(tmp_path / "docs")
        api_packages = None

    apidoc.on_build_start(ConfigNone())
    assert len(calls) == 0


def test_on_build_start_error_handling(tmp_path, monkeypatch, caplog):
    """Verify on_build_start error handling in non-strict and strict modes."""
    import logging
    import pytest
    from golem.plugins import apidoc

    def failing_generate_api_docs(**kwargs):
        raise RuntimeError("Generation failed boom")

    monkeypatch.setattr(apidoc, "generate_api_docs", failing_generate_api_docs)

    # Non-strict mode: logs warning, does not raise
    config_lenient = GolemConfig(
        content_dir=str(tmp_path / "docs"),
        api_packages=["some_pkg"],
        strict=False,
    )
    with caplog.at_level(logging.WARNING, logger="golem.plugins.apidoc"):
        apidoc.on_build_start(config_lenient)
    assert "Failed to generate API documentation during build: Generation failed boom" in caplog.text

    # Strict mode: re-raises original exception
    config_strict = GolemConfig(
        content_dir=str(tmp_path / "docs"),
        api_packages=["some_pkg"],
        strict=True,
    )
    with pytest.raises(RuntimeError, match="Generation failed boom"):
        apidoc.on_build_start(config_strict)


def test_build_engine_integration_api_packages(tmp_path):
    """End-to-end integration: BuildEngine generates and compiles API docs when api_packages is configured."""
    import sys

    pkg_dir = tmp_path / "e2e_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""E2E Package docstring."""
def calculate(a: int, b: int) -> int:
    """Add two numbers.

    Args:
        a: First number.
        b: Second number.

    Returns:
        Sum of a and b.
    """
    return a + b
''',
        encoding="utf-8",
    )

    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Home\n\nWelcome home.", encoding="utf-8")

    output_dir = tmp_path / "dist"
    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(output_dir),
        plugins=["golem.plugins.apidoc"],
        api_packages=["e2e_pkg"],
        api_output_dir="api",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        engine = BuildEngine(config)
        compiled = engine.build_site()

        # Check .adoc was generated in content_dir / api
        generated_adoc = content_dir / "api" / "e2e_pkg.adoc"
        assert generated_adoc.exists()

        # Check HTML was generated in output_dir / api
        generated_html = output_dir / "api" / "e2e_pkg.html"
        assert generated_html.exists()
        assert generated_html in compiled

        html_text = generated_html.read_text(encoding="utf-8")
        assert "E2E Package" in html_text or "e2e_pkg" in html_text
        assert "calculate" in html_text
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))


def test_build_engine_strict_mode_raises_when_apidoc_fails(tmp_path, monkeypatch) -> None:
    """Verify BuildEngine(strict=True) re-raises when apidoc generation fails."""
    import pytest
    from golem.engine import BuildEngine

    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "index.adoc").write_text("= Test\n\nBody", encoding="utf-8")

    config = GolemConfig(
        content_dir=str(content_dir),
        output_dir=str(tmp_path / "dist"),
        plugins=["golem.plugins.apidoc"],
        api_packages=["nonexistent_pkg_that_will_fail"],
        strict=True,
    )

    def _mock_generate_fail(*args, **kwargs):
        raise RuntimeError("Simulated apidoc failure during build")

    from golem.plugins import apidoc

    monkeypatch.setattr(apidoc, "generate_api_docs", _mock_generate_fail)

    engine = BuildEngine(config)
    with pytest.raises(RuntimeError, match="Simulated apidoc failure during build"):
        engine.build_site()


def _find_nodes(root, node_type):
    """Yield every node of *node_type* in the tree rooted at *root*."""
    if isinstance(root, node_type):
        yield root
    if hasattr(root, "get_child_collections"):
        for collection in root.get_child_collections().values():
            for child in collection:
                yield from _find_nodes(child, node_type)
    else:
        for collection_name in ("blocks", "items"):
            for child in getattr(root, collection_name, None) or []:
                yield from _find_nodes(child, node_type)


def test_apidoc_docstring_examples_emit_sidebar(tmp_path):
    """Verify that docstring Examples sections render as sidebar-column."""
    from asciidoctrine import parse_to_ast
    from asciidoctrine.nodes import Sidebar
    from asciidoctrine.resolver import ASGResolver
    from golem.plugins import apidoc
    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "sidebar_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Sidebar package."""
def process_data(data: list[str]) -> dict:
    """Process input data.

    Examples:
        >>> process_data(["a", "b"])
        {'count': 2}

    More examples:
        >>> process_data([])
        {'count': 0}
    """
    return {"count": len(data)}
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        api = AsciiDocApi(search_paths=[tmp_path])
        nodes = api.get_asg_nodes("sidebar_pkg.process_data")
        assert nodes, "expected at least one node"

        sidebars = [n for root in nodes for n in _find_nodes(root, Sidebar)]
        assert sidebars, "expected at least one Sidebar node"
        for sidebar in sidebars:
            assert sidebar.attributes.get("role") == "sidebar-column", sidebar.attributes
            assert sidebar.blocks, "sidebar should carry content blocks"

        raw_doc = "= Sidebar Test\n\ngolem.apidoc::sidebar_pkg.process_data[depth=all]\n"
        ast = parse_to_ast(raw_doc)
        asg = ASGResolver(ast).resolve_to_ast(ast)
        html = render_body(apidoc.on_asg_created(asg=asg))

        assert 'class="sidebarblock sidebar-column"' in html, html
        # The sidebars must sit beside the prose in a two-column split row, not
        # stacked below it (B0's split-row layout piece).
        assert 'class="openblock split-row"' in html, html
        assert 'class="openblock prose-column"' in html, html
        assert "process_data" in html
        assert "count" in html
    finally:
        sys.path.remove(str(tmp_path))


def test_apidoc_docstring_without_examples_has_no_split_row(tmp_path):
    """Prose-only docstrings must keep the plain layout (no empty grid wrappers)."""
    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "plain_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Plain package."""
def plain(text: str) -> str:
    """Return the text unchanged."""
    return text
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        api = AsciiDocApi(search_paths=[tmp_path])
        nodes = api.get_asg_nodes("plain_pkg.plain")
        html = "\n".join(render_body(node) for node in nodes)
        assert "split-row" not in html, html
        assert "sidebar-column" not in html, html
    finally:
        sys.path.remove(str(tmp_path))


def test_apidoc_docstring_params_render_description_list(tmp_path):
    """Verify that docstring Parameters sections render as DescriptionList."""
    from asciidoctrine.nodes import DescriptionList
    from golem.plugins.apidoc import AsciiDocApi

    pkg_dir = tmp_path / "param_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Param package."""
def compute(x: int, y: float = 1.0) -> float:
    """Compute a value.

    Args:
        x: The first parameter.
        y: The second parameter with default.
    """
    return x * y
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        api = AsciiDocApi(search_paths=[tmp_path])
        nodes = api.get_asg_nodes("param_pkg.compute")
        assert nodes, "expected at least one node"

        lists = [n for root in nodes for n in _find_nodes(root, DescriptionList)]
        assert lists, "expected a DescriptionList for the parameters"
        terms = [t for dlist in lists for item in dlist.items for t in item.terms]
        joined = " ".join(_node_text(term) for term in terms)
        assert "x" in joined, joined
        assert "y" in joined, joined
    finally:
        sys.path.remove(str(tmp_path))


def test_apidoc_docstring_returns_raises_render_admonition(tmp_path):
    """Verify that docstring Returns/Raises sections render as Admonition."""
    from asciidoctrine.nodes import Admonition
    from golem.plugins.apidoc import AsciiDocApi

    pkg_dir = tmp_path / "admon_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Admon package."""
def divide(a: float, b: float) -> float:
    """Divide two numbers.

    Returns:
        float: The quotient.

    Raises:
        ZeroDivisionError: If b is zero.
    """
    if b == 0:
        raise ZeroDivisionError("Cannot divide by zero")
    return a / b
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        api = AsciiDocApi(search_paths=[tmp_path])
        nodes = api.get_asg_nodes("admon_pkg.divide")
        assert nodes, "expected at least one node"

        admonitions = [n for root in nodes for n in _find_nodes(root, Admonition)]
        assert admonitions, "expected at least one Admonition"
        raises_blocks = [a for a in admonitions if a.variant == "warning"]
        assert raises_blocks, "expected a warning admonition for the raises section"

        text = " ".join(_node_text(block) for admonition in raises_blocks for block in admonition.blocks)
        assert "ZeroDivisionError" in text, text
        assert "zero" in text.lower(), text
    finally:
        sys.path.remove(str(tmp_path))


def _node_text(node):
    """Return the plain text carried by a node, descending into children."""
    value = getattr(node, "value", None)
    if isinstance(value, str):
        return value
    parts = [getattr(inline, "value", "") for inline in getattr(node, "inlines", None) or []]
    parts.extend(_node_text(term) for term in getattr(node, "terms", None) or [])
    parts.extend(_node_text(block) for block in getattr(node, "blocks", None) or [])
    return "".join(part for part in parts if isinstance(part, str))


def test_apidoc_param_description_keeps_inline_markup(tmp_path):
    """Parameter descriptions must keep their inline AsciiDoc markup."""
    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "markup_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Markup package."""
def run(mode: str) -> None:
    """Run in a mode.

    Args:
        mode: The mode, e.g. ``fast`` or *safe*. See <<limits>>.
    """
    pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        api = AsciiDocApi(search_paths=[tmp_path])
        nodes = api.get_asg_nodes("markup_pkg.run")
        html = "\n".join(render_body(node) for node in nodes)

        # Inline markup must survive: a flattened-text fallback would have
        # re-parsed plain text and lost these tags.
        assert "<code>fast</code>" in html, html
        assert "<strong>safe</strong>" in html, html
        assert 'class="xref"' in html, html
    finally:
        sys.path.remove(str(tmp_path))


def test_apidoc_docstring_heading_survives_param_sections(tmp_path):
    """An authored sub-heading must render as a heading, not flattened text."""
    from golem.plugins.apidoc import AsciiDocApi
    from golem.renderer import render_body

    pkg_dir = tmp_path / "mixed_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Mixed package."""
def sync(options: dict) -> None:
    """Sync a config.

    === Sync Options
    Tune how the sync runs.

    Args:
        options: Sync options.
    """
    pass
''',
        encoding="utf-8",
    )

    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        api = AsciiDocApi(search_paths=[tmp_path])
        nodes = api.get_asg_nodes("mixed_pkg.sync")
        html = "\n".join(render_body(node) for node in nodes)

        # The sub-heading must render as a real heading, not flattened text, and
        # must nest below the function heading.
        heading = re.search(r"<h(\d)[^>]*>Sync Options</h\1>", html)
        assert heading, f"expected a heading for 'Sync Options': {html}"
        assert heading.group(1) == "3", html
        assert "Tune how the sync runs." in html
        # The params list survives after the sub-heading, whichever way the
        # upstream bridge chooses to wrap the term.
        assert re.search(r"<dt>\s*(?:<code>)?options(?:</code>)?\s*</dt>", html), html
        assert "Sync options." in html
    finally:
        sys.path.remove(str(tmp_path))
