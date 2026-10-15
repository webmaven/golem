"""Tripwire tests for upstream deficiencies golem currently works around.

Each test below is marked `xfail(strict=True)`: it documents a real gap in an
upstream dependency (`asciidoctrine` / `asciidoctype`) and asserts the behaviour
golem needs. The test xfails while the gap remains, and **fails loudly as XPASS**
the moment upstream fixes it.

When a test starts failing as XPASS, the corresponding workaround in
`src/golem/plugins/apidoc/core/api.py` should be deleted and the upstream
behaviour used directly instead.

Both gaps are reported upstream (see `.kilo/plans/upstream-issues.md`):
* asciidoctrine -- `[sidebar]` on `====` delimiters is *not* translated into a
  `Sidebar` node (only the `****` delimiter is), so `sidebar.html` is
  unreachable for `====`-authored sidebars.
* asciidoctype -- `listing.html` ignores the `role` attribute, so a source
  block cannot be restyled through a role.
"""

from __future__ import annotations

import pytest

import asciidoctype
import asciidoctrine


def _top_level_blocks(source: str) -> list:
    """Parse *source* and return its top-level ASG blocks."""
    ast = asciidoctrine.parse_to_ast(source)
    return list(getattr(ast, "blocks", None) or [])


def _block_names(blocks: list) -> list[str]:
    """Return the lowercase node names of *blocks*."""
    return [getattr(block, "name", "").lower() for block in blocks]


@pytest.mark.xfail(
    strict=True,
    reason="UPSTREAM asciidoctrine: `[sidebar]` on `====` yields an `example`, not a `sidebar` node",
)
def test_sidebar_style_on_equals_delimiters_yields_sidebar_node():
    """`[sidebar]` should produce a `sidebar` node just like the `****` delimiter does."""
    assert "sidebar" in _block_names(_top_level_blocks("[sidebar]\n====\nSidebar prose.\n====\n"))


def test_star_delimited_block_yields_sidebar_node():
    """Regression guard: the `****` delimiter already yields a `sidebar` node."""
    assert "sidebar" in _block_names(_top_level_blocks("****\nSidebar prose.\n****\n"))


@pytest.mark.xfail(
    strict=True,
    reason="UPSTREAM asciidoctype: `listing.html` ignores `role`, so role-based styling is impossible",
)
def test_listing_template_honours_role():
    """A source block carrying a role should surface that role in the rendered class."""
    from asciidoctrine.nodes import Listing, Text

    renderer = asciidoctype.AsciiDoctypeRenderer(target_format="html5", strict=False)
    block = Listing(
        inlines=[Text("print('hi')")],
        attributes={"style": "source", "language": "python", "role": "sidebar-column"},
    )
    html = renderer.render(block.to_dict())
    assert "sidebar-column" in html, html
