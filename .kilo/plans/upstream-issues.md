# Upstream Issues

Issue text for deficiencies found in golem's dependencies while implementing
Wave 2. Filed text only — post to the repos below and link the issues back here.

| Dependency | Repo | Issue |
|------------|------|-------|
| `asciidoctrine` | AsciiDoctrine/asciidoctrine | `[sidebar]` on `====` delimiters is not translated into a `Sidebar` node |
| `asciidoctype` | AsciiDoctrine/asciidoctype | `listing.html` ignores the `role` attribute |

Both are covered by strict `xfail` tripwires in `tests/test_upstream_tripwires.py`.
When a tripwire reports XPASS, delete the matching workaround in golem and use the
upstream behaviour.

---

## Issue 1 — asciidoctrine: `[sidebar]` on `====` delimiters yields `example`, not `sidebar`

**Title:** `[sidebar]` block style on `====` delimiters is not translated into a `Sidebar` node

**Labels:** bug, parsing, blocks

**Body:**

Assigning the `sidebar` block style to `====` delimiters does not produce a
`Sidebar` node. The `****` delimiter does, so the two spellings of the same block
disagree.

Repro:

```python
>>> import asciidoctrine
>>> ast = asciidoctrine.parse_to_ast("****\nSidebar prose.\n****\n")
>>> [b.name for b in ast.resolve_to_ast(ast).blocks]
['sidebar']
>>> ast = asciidoctrine.parse_to_ast("[sidebar]\n====\nSidebar prose.\n====\n")
>>> [b.name for b in ast.resolve_to_ast(ast).blocks]
['example']
>>> [b.attributes for b in ast.resolve_to_ast(ast).blocks]
[{'style': 'sidebar', '1': 'sidebar', 'positional': ['sidebar']}]
```

The style is left as a plain `style` attribute, so `sidebar.html` is never reached
and the block renders via `example.html` (`.exampleblock`) instead.

Expected: the second form yields a `sidebar` node, matching `****`.

Notes:
- `nodes.Sidebar` exists (`nodes.py`) but `lark_parser.py` never constructs it
  from the `====` path; the block-style handling around lines 418-504 falls
  through to the generic `attributes["style"] = v` branch.
- Impact: docstrings and prose authored with `[sidebar]` + `====` cannot reach the
  sidebar template, even though the `****` spelling works.

---

## Issue 2 — asciidoctype: `listing.html` ignores the `role` attribute

**Title:** `listing.html` does not emit the `role` attribute as a CSS class

**Labels:** bug, templates, html5

**Body:**

`section.html` and `sidebar.html` mirror `attributes["role"]` into the element's
CSS class, but `listing.html` drops it entirely — `role` is not emitted as an
attribute or as a class.

Repro:

```python
>>> import asciidoctrine
>>> from asciidoctrine.nodes import Listing, Text
>>> import asciidoctype
>>> renderer = asciidoctype.AsciiDoctypeRenderer(target_format="html5")
>>> block = Listing(
...     inlines=[Text("print('hi')")],
...     attributes={"style": "source", "language": "python", "role": "sidebar-column"},
... )
>>> renderer.render(block.to_dict())
'<div class="listingblock"><div class="content"><pre class="highlight python"><code class="language-python">print(\'hi\')</code></pre></div></div>'
```

Expected: `sidebar-column` appears in the rendered class list (e.g.
`class="listingblock sidebar-column"`), consistent with `section.html` /
`sidebar.html`.

Notes:
- `asyncioctype/core_templates/html5/listing.html:8-17` never reads
  `node.get('attributes', {}).get('role')`.
- Impact: any consumer that styles source blocks via roles (e.g. golem's API
  reference, which puts examples in a `sidebar-column` sidebar) has to work
  around it by wrapping the listing in another node.