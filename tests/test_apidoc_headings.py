from __future__ import annotations

from pathlib import Path
import re
import sys

import asciidoctrine
from asciidoctrine.nodes import DiscreteHeading, Section
from asciidoctrine.resolver import ASGResolver
from golem.plugins import apidoc
from golem.renderer import render_body


def _find_all_sections(node) -> list[Section]:
    """Recursively collect all Section nodes."""
    found: list[Section] = []
    if isinstance(node, Section):
        found.append(node)
    blocks = getattr(node, "blocks", []) or []
    for b in blocks:
        found.extend(_find_all_sections(b))
    return found


def _find_all_headings(node) -> list[DiscreteHeading]:
    """Recursively collect all DiscreteHeading nodes."""
    found: list[DiscreteHeading] = []
    if isinstance(node, DiscreteHeading):
        found.append(node)
    blocks = getattr(node, "blocks", []) or []
    for b in blocks:
        found.extend(_find_all_headings(b))
    return found


def test_apidoc_class_headings_nested_in_level_3(tmp_path: Path):
    """Assert golem.apidoc in a level-3 section enforces predictable absolute heading hierarchy."""
    pkg_dir = tmp_path / "sample_worker_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Worker package."""
class Worker:
    """A background worker."""
    active: bool = True
    """Whether worker is active."""

    def perform_job(self, name: str) -> str:
        """Perform a designated job.

        === Job Details
        Additional details about the job.
        """
        return f"Done: {name}"
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= System Manual

== Operations

=== Worker Integration

golem.apidoc::sample_worker_pkg.Worker[]
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        asg = ASGResolver(ast).resolve_to_ast(ast)
        transformed = apidoc.on_asg_created(asg=asg)

        # 1. Assert ASG nodes have absolute-level set correctly
        sections = _find_all_sections(transformed)

        # Locate class section
        class_sec = next(
            (
                s
                for s in sections
                if s.title
                and "class Worker"
                in "".join(
                    str(getattr(t, "value", t)) for t in (s.title.inlines if hasattr(s.title, "inlines") else [s.title])
                )
            ),
            None,
        )
        assert class_sec is not None, "Class section not found in ASG"
        assert getattr(class_sec, "absolute_level", None) == 2 or class_sec.to_dict().get("absolute-level") == 2, (
            f"Expected class absolute-level=2, got {getattr(class_sec, 'absolute_level', None)}"
        )

        # Locate method section
        method_sec = next(
            (
                s
                for s in sections
                if s.title
                and "perform_job"
                in "".join(
                    str(getattr(t, "value", t)) for t in (s.title.inlines if hasattr(s.title, "inlines") else [s.title])
                )
            ),
            None,
        )
        assert method_sec is not None, "Method section not found in ASG"
        assert getattr(method_sec, "absolute_level", None) == 3 or method_sec.to_dict().get("absolute-level") == 3, (
            f"Expected method absolute-level=3, got {getattr(method_sec, 'absolute_level', None)}"
        )

        # Locate attributes section
        attr_sec = next(
            (
                s
                for s in sections
                if s.title
                and "Attributes"
                in "".join(
                    str(getattr(t, "value", t)) for t in (s.title.inlines if hasattr(s.title, "inlines") else [s.title])
                )
            ),
            None,
        )
        assert attr_sec is not None, "Attributes section not found in ASG"
        assert getattr(attr_sec, "absolute_level", None) == 3 or attr_sec.to_dict().get("absolute-level") == 3, (
            f"Expected attributes absolute-level=3, got {getattr(attr_sec, 'absolute_level', None)}"
        )

        # 2. Assert HTML rendering produces predictable <h2>, <h3>, <h4> elements
        html = render_body(transformed)

        # Parent level-3 section stays <h3>
        assert "<h3>Worker Integration</h3>" in html or re.search(r"<h3[^>]*>Worker Integration</h3>", html)

        # Class heading must render as <h2>
        assert re.search(r"<h2[^>]*>.*Worker.*</h2>", html), f"Class heading did not render as <h2>: {html}"

        # Method and Attributes headings must render as <h3>
        assert re.search(r"<h3[^>]*>.*perform_job.*</h3>", html), f"Method heading did not render as <h3>: {html}"
        assert re.search(r"<h3[^>]*>Attributes</h3>", html), f"Attributes heading did not render as <h3>: {html}"

        # Job Details in method docstring should render as <h4>
        assert re.search(r"<h4[^>]*>.*Job Details.*</h4>", html), f"Job Details heading did not render as <h4>: {html}"
    finally:
        sys.path.remove(str(tmp_path))


def test_apidoc_function_headings_nested_in_level_4(tmp_path: Path):
    """Assert golem.apidoc in a level-4 section enforces absolute-level=2 on function."""
    pkg_dir = tmp_path / "sample_fn_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Function package."""
def compute_metrics(dataset: str) -> dict[str, int]:
    """Compute dataset metrics.

    === Metric Parameters
    Parameters for metrics calculation.
    """
    return {"count": 1}
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Operations Guide

== Core Systems

=== Analytics

==== Metric Processing

golem.apidoc::sample_fn_pkg.compute_metrics[]
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        asg = ASGResolver(ast).resolve_to_ast(ast)
        transformed = apidoc.on_asg_created(asg=asg)

        sections = _find_all_sections(transformed)
        func_sec = next(
            (
                s
                for s in sections
                if s.title
                and "compute_metrics"
                in "".join(
                    str(getattr(t, "value", t)) for t in (s.title.inlines if hasattr(s.title, "inlines") else [s.title])
                )
            ),
            None,
        )
        assert func_sec is not None, "Function section not found in ASG"
        assert getattr(func_sec, "absolute_level", None) == 2 or func_sec.to_dict().get("absolute-level") == 2, (
            f"Expected function absolute-level=2, got {getattr(func_sec, 'absolute_level', None)}"
        )

        html = render_body(transformed)

        # Parent level-4 section stays <h4>
        assert re.search(r"<h4[^>]*>Metric Processing</h4>", html)

        # Function heading must render as <h2> regardless of being inside level-4 section
        assert re.search(r"<h2[^>]*>.*compute_metrics.*</h2>", html), f"Function heading did not render as <h2>: {html}"

        # Sub-heading within function must render as <h3> or <h4>
        assert re.search(r"<h[34][^>]*>.*Metric Parameters.*</h[34]>", html), f"Docstring heading missing: {html}"
    finally:
        sys.path.remove(str(tmp_path))


def test_apidoc_discrete_heading_rendering():
    """Assert discrete headings with absolute-level render to matching HTML heading elements."""
    heading = DiscreteHeading(
        level=2,
        title=asciidoctrine.nodes.Title([asciidoctrine.nodes.Text("Floating Title")]),
        absolute_level=3,
    )
    html = render_body(heading)
    assert "<h3" in html
    assert "Floating Title</h3>" in html
    assert "discrete" in html


def test_apidoc_headings_with_heading_level_offset(tmp_path: Path):
    """Assert heading_level_offset adjusts absolute-level accordingly."""
    pkg_dir = tmp_path / "sample_offset_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""Offset package."""
class Service:
    """A service class."""
    def run(self) -> None:
        """Run service."""
        pass
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= Offset Manual

golem.apidoc::sample_offset_pkg.Service[heading_level_offset=1]
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        asg = ASGResolver(ast).resolve_to_ast(ast)
        transformed = apidoc.on_asg_created(asg=asg)

        sections = _find_all_sections(transformed)
        class_sec = next(
            (
                s
                for s in sections
                if s.title
                and "class Service"
                in "".join(
                    str(getattr(t, "value", t)) for t in (s.title.inlines if hasattr(s.title, "inlines") else [s.title])
                )
            ),
            None,
        )
        assert class_sec is not None
        # With offset 1, class absolute_level is 2 + 1 = 3
        assert getattr(class_sec, "absolute_level", None) == 3 or class_sec.to_dict().get("absolute-level") == 3

        method_sec = next(
            (
                s
                for s in sections
                if s.title
                and "run"
                in "".join(
                    str(getattr(t, "value", t)) for t in (s.title.inlines if hasattr(s.title, "inlines") else [s.title])
                )
            ),
            None,
        )
        assert method_sec is not None
        # With offset 1, method absolute_level is 3 + 1 = 4
        assert getattr(method_sec, "absolute_level", None) == 4 or method_sec.to_dict().get("absolute-level") == 4

        html = render_body(transformed)
        assert re.search(r"<h3[^>]*>.*Service.*</h3>", html)
        assert re.search(r"<h4[^>]*>.*run.*</h4>", html)
    finally:
        sys.path.remove(str(tmp_path))


def test_wcag_heading_hierarchy_no_skipped_levels(tmp_path: Path):
    """Verify WCAG 2.1 SC 1.3.1 compliance: document has progressive heading sequence without skips."""
    pkg_dir = tmp_path / "sample_wcag_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        '''"""WCAG validation package."""
class AppController:
    """Controller class."""
    def handle_request(self, path: str) -> str:
        """Handle incoming request.

        === Request Lifecycle
        Lifecycle documentation.
        """
        return path
''',
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        raw_doc = """= API Reference

== Controller Section

golem.apidoc::sample_wcag_pkg.AppController[]
"""
        ast = asciidoctrine.parse_to_ast(raw_doc)
        asg = ASGResolver(ast).resolve_to_ast(ast)
        transformed = apidoc.on_asg_created(asg=asg)
        html = render_body(transformed)

        # Extract all heading tags in document order
        heading_tags = re.findall(r"<h([1-6])[^>]*>", html)
        levels = [int(h) for h in heading_tags]
        assert len(levels) >= 3, f"Expected multiple headings, found: {levels}"

        # WCAG 2.1 SC 1.3.1: No heading level may be skipped (e.g. h2 -> h4 without h3)
        for i in range(1, len(levels)):
            prev, curr = levels[i - 1], levels[i]
            # Heading can be at same level, or up to prev + 1, or jump back to a higher level
            assert curr <= prev + 1, f"Heading level skipped from h{prev} to h{curr} at index {i}: sequence={levels}"
    finally:
        sys.path.remove(str(tmp_path))


def test_standard_sections_unaffected():
    """Verify standard sections without absolute-level render normally according to document-relative depth."""
    raw_doc = """= Document

== Level 1

=== Level 2

==== Level 3
"""
    ast = asciidoctrine.parse_to_ast(raw_doc)
    asg = ASGResolver(ast).resolve_to_ast(ast)
    html = render_body(asg)

    assert re.search(r"<h2[^>]*>Level 1</h2>", html)
    assert re.search(r"<h3[^>]*>Level 2</h3>", html)
    assert re.search(r"<h4[^>]*>Level 3</h4>", html)
