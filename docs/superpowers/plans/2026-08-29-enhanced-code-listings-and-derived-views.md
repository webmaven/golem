# Enhanced Code Listings & AsciiDoc Derived Renderings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement non-overlapping listing headers with metadata badges and copy buttons, plus build-time multi-view derived renderings (`source`, `asg`, `html`, `preview`) for AsciiDoc code listings in Golem.

**Architecture:** 
1. Replace CSS pseudo-element language badges with a semantic `<header class="listing-header">` in a dedicated Chameleon `listing.html` template.
2. Provide a derived view transformation pipeline in `src/golem/renderer.py` (and supporting transform helpers) that parses `render="..."` / `views="..."` attributes on AsciiDoc listing blocks to synthesize multi-tab views at build time.
3. Add accessible, zero-dependency vanilla JS and CSS to `skeleton.pt` for interactive tab switching and scoped clipboard copying.

**Tech Stack:** Python 3.14, `asciidoctrine`, `asciidoctype`, Chameleon ZPT templates, Pygments, Semantic HTML5/CSS3, Vanilla JavaScript.

## Global Constraints
- Pure vanilla HTML/CSS and lightweight JS — zero external JS frameworks or heavy dependencies.
- Zero-JS baseline: Listing titles and language badges must render statically; tabs degrade gracefully without JS.
- Strict backward compatibility with all existing AsciiDoc syntax highlighting and callouts.
- All tests must pass cleanly (`pytest`).

---

### Task 1: Single Listing Header Template & CSS

**Files:**
- Create: `src/golem/templates/default/listing.html`
- Modify: `src/golem/renderer.py:40-90`
- Modify: `src/golem/templates/default/skeleton.pt:340-420`
- Test: `tests/test_renderer.py`

**Interfaces:**
- Consumes: ASG `listing` block dictionary (`attributes`, `title`, `inlines`, `value`).
- Produces: Semantic HTML `<figure class="listingblock">` containing `<header class="listing-header">` (title, test/shared badges, language badge, copy button) and `<div class="listing-content"><pre><code>...</code></pre></div>`.

- [ ] **Step 1: Write failing test in `tests/test_renderer.py` for listing header structure**

```python
def test_render_listing_header_structure():
    """Verify listing rendering generates semantic listing-header with title, badges, and copy button."""
    asg = {
        "name": "listing",
        "type": "block",
        "title": "sample.py",
        "value": "print('hello')",
        "attributes": {
            "language": "python",
            "role": "test shared",
        },
    }
    html = render_body(asg)
    assert '<figure class="listingblock"' in html
    assert '<header class="listing-header">' in html
    assert '<span class="listing-title">sample.py</span>' in html
    assert 'class="badge badge-test"' in html
    assert 'class="badge badge-shared"' in html
    assert 'class="badge badge-lang">PYTHON</span>' in html
    assert 'class="listing-copy-btn"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_renderer.py::test_render_listing_header_structure -v`  
Expected: FAIL with `AssertionError: assert '<figure class="listingblock"' in html`

- [ ] **Step 3: Create `src/golem/templates/default/listing.html` and update `render_body` search paths**

In `src/golem/renderer.py`, update `render_body` to include `src/golem/templates/default` (or package template path) in `search_paths` by default.
In `src/golem/templates/default/listing.html`, implement the Chameleon template rendering the `.listing-header` and `.listing-content`.

- [ ] **Step 4: Update `skeleton.pt` CSS for `.listing-header` and remove overlapping `pre::before` rules**

Remove lines 375–540 in `src/golem/templates/default/skeleton.pt` that use `pre.highlight::before` for language badge overlays.
Add modern CSS flexbox rules for `.listingblock`, `.listing-header`, `.listing-title`, `.listing-actions`, `.badge`, `.badge-lang`, `.badge-test`, `.badge-shared`, and `.listing-copy-btn`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_renderer.py -v`  
Expected: PASS

- [ ] **Step 6: Commit changes**

```bash
git add src/golem/templates/default/listing.html src/golem/renderer.py src/golem/templates/default/skeleton.pt tests/test_renderer.py
git commit -m "feat: add semantic listing-header with badges and copy button"
```

---

### Task 2: Client-Side Copy Button & Tab Interaction Script

**Files:**
- Modify: `src/golem/templates/default/skeleton.pt:900-990`
- Test: `tests/test_renderer.py`

**Interfaces:**
- Consumes: DOM `.listingblock`, `.listing-copy-btn`, `.tab-btn`, `.tab-pane`.
- Produces: Clipboard copy action with temporary visual feedback; tab panel switching with ARIA updates.

- [ ] **Step 1: Write test verifying copy button accessibility attributes and icons**

```python
def test_listing_copy_button_markup():
    asg = {"name": "listing", "type": "block", "value": "x = 1", "attributes": {"language": "python"}}
    html = render_body(asg)
    assert 'aria-label="Copy code to clipboard"' in html
    assert 'class="icon-copy"' in html
```

- [ ] **Step 2: Run test to verify it passes/fails**

Run: `pytest tests/test_renderer.py::test_listing_copy_button_markup -v`

- [ ] **Step 3: Add lightweight vanilla JS in `skeleton.pt`**

Add script handling:
1. `.listing-copy-btn` click: find nearest `.listingblock`, locate active `pre code` text, copy to `navigator.clipboard`, show checked icon for 2 seconds.
2. `.tab-btn` click: switch `aria-selected`, toggle `active` class and `hidden` attribute on corresponding `.tab-pane`.

- [ ] **Step 4: Run full test suite to ensure no regressions**

Run: `pytest -v`  
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add src/golem/templates/default/skeleton.pt tests/test_renderer.py
git commit -m "feat: add client-side clipboard copy and tab switching handlers"
```

---

### Task 3: AsciiDoc Derived Multi-View Compilation Engine

**Files:**
- Create: `src/golem/views.py`
- Modify: `src/golem/renderer.py`
- Modify: `src/golem/templates/default/listing.html`
- Modify: `src/golem/templates/default/skeleton.pt` (tab styles)
- Test: `tests/test_derived_views.py`

**Interfaces:**
- Consumes: Listing node with `attributes.get("render")` or `views` / `display` / `formats` attribute (e.g. `"source,asg,html,preview"`).
- Produces: Generated multi-view structure containing tabs and tab panels for each requested view (`source`, `asg`, `html`, `preview`).

- [ ] **Step 1: Write failing tests for derived views in `tests/test_derived_views.py`**

```python
from golem.renderer import render_body

def test_asciidoc_derived_views_rendering():
    """Verify render='source,asg,html,preview' produces multi-tab container with all four representations."""
    asg = {
        "name": "listing",
        "type": "block",
        "title": "Admonition Example",
        "value": "NOTE: This is a note.",
        "attributes": {
            "language": "asciidoc",
            "render": "source,asg,html,preview",
        },
    }
    html = render_body(asg)
    assert 'class="listingblock multi-view"' in html
    assert 'role="tablist"' in html
    assert 'data-tab="source"' in html
    assert 'data-tab="asg"' in html
    assert 'data-tab="html"' in html
    assert 'data-tab="preview"' in html
    # Check that ASG tab contains JSON
    assert '"name": "document"' in html or '"name": "admonition"' in html
    # Check that HTML tab contains HTML source
    assert '&lt;div class="admonitionblock note"&gt;' in html or '<div class="admonitionblock note">' in html
    # Check that Preview tab contains live rendered HTML
    assert '<div class="admonitionblock note">' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_derived_views.py -v`  
Expected: FAIL

- [ ] **Step 3: Implement `src/golem/views.py` for AsciiDoc snippet view derivation**

Implement `generate_asciidoc_views(code_text: str, views: list[str], highlighter=None) -> list[dict]`:
- `source`: highlighted AsciiDoc
- `asg`: parsed AST $\to$ ASG $\to$ formatted JSON $\to$ highlighted JSON
- `html`: rendered HTML markup string $\to$ highlighted HTML
- `preview`: rendered HTML markup string $\to$ raw HTML sandbox

- [ ] **Step 4: Integrate `generate_asciidoc_views` into `src/golem/renderer.py` and `listing.html`**

Update `listing.html` to check for `derived_views` and render the tab bar (`role="tablist"`) and tab panels (`role="tabpanel"`).
Add CSS for `.listing-tabs`, `.tab-btn`, `.tab-pane`, `.rendered-preview` in `skeleton.pt`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_derived_views.py -v`  
Expected: PASS

- [ ] **Step 6: Test attribute aliases (`views`, `display`, `formats`) and subset views (`render="source,preview"`)**

Add tests in `tests/test_derived_views.py` for aliases and subsets; verify they all pass.

- [ ] **Step 7: Commit changes**

```bash
git add src/golem/views.py src/golem/renderer.py src/golem/templates/default/listing.html src/golem/templates/default/skeleton.pt tests/test_derived_views.py
git commit -m "feat: implement AsciiDoc multi-view derived rendering engine"
```

---

### Task 4: Documentation, Integration Verification & Visual Audit

**Files:**
- Modify: `docs/user-guide/authoring.adoc`
- Modify: `docs/developer-guide/theme-development.adoc`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: End-to-end `.adoc` pages with single listings and multi-view derived listings.
- Produces: Fully compiled static documentation site with validated listing components.

- [ ] **Step 1: Add end-to-end integration test in `tests/test_engine.py`**

Compile a sample page containing both standard code listings and `render="source,asg,html,preview"` listings using `BuildEngine`. Verify zero warnings and valid generated HTML.

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_engine.py -k "listing" -v`

- [ ] **Step 3: Update documentation in `docs/user-guide/authoring.adoc`**

Document the enhanced single listing header and the `render="source,asg,html,preview"` feature with interactive examples.

- [ ] **Step 4: Run full test suite across the repository**

Run: `pytest`  
Expected: All tests PASS.

- [ ] **Step 5: Commit changes**

```bash
git add docs/user-guide/authoring.adoc docs/developer-guide/theme-development.adoc tests/test_engine.py
git commit -m "docs: update documentation for enhanced code listings and derived views"
```
