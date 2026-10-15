# Reconstruction Plan: Waves 2-8 Implementation

## Status: Wave 1 Complete | Wave 2 Layout Complete (B0-B13 done, B5 remaining)

**Unit suite: 611 passed, 2 xfailed** (full `tests/`). `ruff check`/`format` clean.
`mypy src tests` reports only the pre-existing repo-wide `asciidoctype`
"missing library stubs" errors (also present in untouched `staleness.py` /
`test_staleness.py`); no new errors introduced.

**E2E: `golem build --clean` completed — 62 pages, zero failures.** All four real
`golem.apidoc::` macro splices (`docs/plugins/source-links.adoc:164`,
`nav-helpers.adoc:145`, `index-glossary.adoc:213/217`, `reference/apidoc.adoc:48`) resolved:
- `0` warning admonitions, `0` "Could not resolve" messages
- `dist/plugins/nav-helpers.html` renders `class="sidebarblock sidebar-column"`
  wrapping a syntax-highlighted `figure.listingblock` (PYTHON badge + copy button)
- parameters render as `<dl class="dlist">` with `<dt>home_url (str | None)</dt>`
  and inline `<code>` markup preserved

**Handoff state (verified 2026-10-15):** the Session 2 cluster above is complete in
the working tree but **not yet committed** (last commit `7dc932f`); the next
increment — commit checkpoint, move of `RECONSTRUCTION.md` into `.kilo/plans/`, B5,
Wave 3 (#16), Wave 4 (#19/#20/#23/#24/#27/#28/#30) — is specified in
`.kilo/plans/1792091844188-wave3-wave4-plan.md`.

### Session 2 additions (B1, B7, B2′ + B3-B13 cluster)

- **B0 split-row wrapper (was missing):** B0a emitted `Sidebar` nodes but nothing
  emitted the `.split-row` grid container, so examples rendered as full-width
  sticky blocks under the prose. `_docstring_nodes()` now wraps example-bearing
  docstrings in `Open(role="split-row")` > `Open(role="prose-column")` + sidebars,
  and CSS makes `.split-row > .content` `display: contents` so the two columns are
  the grid items.
- **B8 ladder implemented per Decision #2** (768/992/1280); the old monotonic
  `#golem-sidebar-right { display: none }` at `max-width: 1100px` was removed.
- **B2′ note:** the reference's `top: 3.5rem`/`4.5rem` offsets assume a sticky
  header. `#golem-header` is *not* sticky in golem, so both sticky panels pin to
  `top: 0` and stay mutually aligned (asserted by a parity test) rather than
  copying the reference constants.
- **B12/B13:** `.member-card` (emitted by `api.py:844`) had zero CSS. It now wears
  the same `--border-rail` rail as `.doc-member`; the standalone signature
  block's `--color-primary` left accent is dropped inside cards so the rail is the
  only left border. No box padding anywhere in the cluster.

| Task | State | Notes |
|------|-------|-------|
| Wave 1 (Detour A) — ASG node construction | DONE | 53 tests green |
| B0a-1 — docstring pipeline rewritten | DONE | `asciidocstring`-native; no Griffe docstring parsing |
| B0a-2 — examples → `Sidebar` nodes | DONE | `role="sidebar-column"` |
| B0a-3 — params, returns, raises builders | DONE | `DescriptionList`, `Admonition` |
| B0a-4 — markup/heading preservation | DONE | passthrough + verbatim description blocks |
| B0a-5 — `.sidebar-column`, `.split-row` CSS | DONE | `golem.css` |
| B0a-6 — regression tests | DONE | 8 tests in `test_plugin_apidoc.py` |
| B0a-7 — lint + typecheck | DONE | clean |
| Upstream tripwires + issue text | DONE | `tests/test_upstream_tripwires.py`, `.kilo/plans/upstream-issues.md` |
| E2E docs build | DONE | 62 pages, no failures (see above) |
| B0b — prose sidebars | N/A | `****` already yields `sidebar` upstream |
| B10 — `flush_right_nav` | DONE | `NavigationHelpersPlugin.flush_right_nav` → `nav-flush-right` class |
| B1 — sticky right TOC sidebar | DONE | `position: sticky` + `align-self: flex-start` + `overflow-y` |
| B2′ — API page sidebar alignment | DONE | both sticky panels pin to viewport top; see note below |
| B7 — source drawer max-height | DONE | `max-height: 400px` + `overflow-y: auto` on `[open]` |
| B3+B4+B6+B11 — `.class-multi-grid` cluster | DONE | uniform h2-h4 sizes, `min-width: 0`, `display: contents` subgrid fix |
| B8/B9 — nav visibility ladder, adjacency | DONE | CSS-only 4-state ladder at 768/992/1280 |
| B12/B13 — `member-card` / `.doc-rail` | DONE | card rail + signature accent stripped; no box padding |
| B5 — table clipping/overflow | PENDING | no `.tableblock` overflow wrapper or test exists; moved to `1792091844188-wave3-wave4-plan.md` Phase 1 |
| Waves 3-8 | TODO | Wave 3 + Wave 4 now specified in `.kilo/plans/1792091844188-wave3-wave4-plan.md` |

Wave 1 (Detour A) is verified complete. Wave 2 (layout) is complete: content
sidebars (B0) render beside prose in a split row, the in-page nav follows the
4-state visibility ladder, and the member-card rail hierarchy is in place.

### E2E build timings (for the record)

The docs build is dominated by the gitignored `docs/api/` tree, which the legacy
`generate_package_docs()` string renderer regenerates on every run and the main
pipeline then parses. Per upstream, `asciidoctrine`'s Earley parser scales with
*length × ambiguity*, so large generated pages — not docstrings — are the cost.
`asciidocstring.parse()` on a short docstring is ~0.29s.

Micro-optimisation already landed while verifying: the returns/raises/deprecated
builders reused the block's own parsed AST nodes instead of re-parsing the semantic
models' flattened text (which cost one `parse_to_ast()` per entry). 33.3s → 29.9s
across the four macro targets. Not worth pursuing further here.

**Measured 2026-10-15 (post Wave 2):** clean build **~700s**, down from **~1000s**
baseline, 62 pages. This direct measurement supersedes the earlier "~5 min"
attribution (exact before/after attribution was never preserved; RECONSTRUCTION.md
§2.1/§5.9 to be updated with this number).

## Key Design Decisions (Resolved)

1. **B0a: docstring pipeline rewritten on `asciidocstring`, not Griffe**
   - Replaced pipeline: `griffe.Docstring` → `format_docstring()` → `asciidocstring.to_asciidoc()` → AsciiDoc string → `asciidoctrine.parse_to_ast()` → ASG nodes. Every section kind was flattened to text, so examples, parameters and raises were unrecoverable.
   - **Decision (as implemented):** `griffe.Docstring` → `asciidocstring.parse()` → `AsciiDocStringDocument` → walk `doc.ast.blocks`, dispatching each block to a typed builder. No AsciiDoc serialization/parsing round-trip for semantics.
   - **Why asciidocstring and not `griffe.parse()`:** Griffe has no AsciiDoc parser — it only understands Google/NumPy/Sphinx. Griffe's correct role in golem is walking *code structure* (modules/classes/functions/attributes). For non-`asciidoc` styles, `asciidocstring.from_griffe()` does the delegation for us and lands on the same `AsciiDocStringDocument`, so downstream builders see one uniform representation.
   - **Two output modes, chosen per block:**
     - Semantic kinds (`examples`, `parameters`, `attributes`, `returns`, `yields`, `receives`, `raises`, `warns`, `deprecated`) → typed ASG nodes: `examples` → `Sidebar(role="sidebar-column")`, params → `DescriptionList`, returns → `Paragraph`+`Listing`, raises/warns → `Admonition`.
     - Every other block → **passed through verbatim**, so authored sub-headings (`=== Job Details`), tables and inline markup survive. (This is what fixed the heading tests: the old `doc.description` string flattened headings away.)
   - **Templates unchanged.** The renderer still resolves `f"{node_name}.html"`, so `Sidebar` → `sidebar.html` and `DescriptionList` → `descriptionlist.html`.
   - **Legacy note:** `format_docstring()` and the string-based renderers (`format_module`/`format_class`/`format_function`/`format_attribute`) are still live — they feed `generate_package_docs()`, which writes `.adoc` files. They are a separate feature from the AST-splicing path and were left alone.

2. **4-state nav visibility (B8): CSS-only via `:has()`**
   - State 1 (hidden): default `#golem-sidebar-right { display: none }`
   - State 2 (visible): `@media (min-width: 768px) { #golem-sidebar-right { display: block } }`
   - State 3 (hidden when sidebars present): `@media (min-width: 992px) { body:has(.sidebar-column) #golem-sidebar-right { display: none } }`
   - State 4 (visible even with sidebars): `@media (min-width: 1280px) { body:has(.sidebar-column) #golem-sidebar-right { display: block } }`
   - **Rationale:** The plan's 1180px is a lost constant (~🎚). Use standard breakpoints as starting points, adjust after measuring actual column widths.

3. **Nav position (B9/B10): CSS `margin-left: auto` for adjacent, `.nav-flush-right` class for forced flush**
   - **Decision:** B9 (adjacent) is the CSS default via `margin-left: auto` on `#golem-wrapper`. B10 adds `nav_helpers.flush_right_nav = True` config flag, which the nav_helpers plugin passes to the template context as `nav_position: "flush-right"`, and the template applies `class="nav-flush-right"` on `#golem-sidebar-right`.
   - **As implemented:** adjacency is the natural flex default (no auto margin); `#golem-sidebar-right.nav-flush-right { margin-left: auto }` is the opt-in escape hatch. An auto margin only resolves when free space exists past the content's `max-width`, i.e. exactly the wide regime where the choice is visible.

4. **`--badge-radius` value: `var(--radius-full)`**
   - Glyph badges are pill-shaped (color/text on colored background). `--radius-full` (9999px) is the natural choice.

## Implementation Tasks (Ordered)

### Wave 2 — Layout (B0 first, then B1-B13) ✅ COMPLETE (B5 pending; see `.kilo/plans/1792091844188-wave3-wave4-plan.md` Phase 1)

#### B0: Content Sidebar Emission (BLOCKER) — DONE

**B0a — apidoc derived sidebars: DONE** (`src/golem/plugins/apidoc/core/api.py`)

- [x] **B0a-1** — Rewrite `_docstring_nodes()` on top of `asciidocstring`. Walks `doc.ast.blocks` and dispatches each block via `_docstring_block_nodes()`. Non-`asciidoc` styles delegate to `asciidocstring.from_griffe()`, **not** `griffe.parse()` (Griffe has no AsciiDoc parser).
- [x] **B0a-2** — Examples → `Sidebar(attributes={"role": "sidebar-column"})` wrapping a source `Listing`. Fires for examples-role blocks **and** bare listings / `====` example blocks.
- [x] **B0a-3** — `parameters`/`attributes` → `DescriptionList` (paired positionally with `DocstringParam`/`DocstringAttribute`); `returns`/`yields`/`receives` → description paragraphs + type `Listing`; `raises`/`warns` → `Admonition` (`warning`/`caution`); `deprecated` → `Admonition(note)`; `:versionadded:`/`:versionchanged:`/`:experimental:` → `Admonition(note)`.
- [x] **B0a-4** — Passthrough for unrecognised blocks, so authored sub-headings (`=== Job Details`), tables and inline markup survive as real nodes. Parameter descriptions reuse the item's own parsed blocks, keeping `<code>`/`<strong>`/`<a class="xref">`.
- [x] **B0a-5** — `.sidebar-column` / `.split-row` CSS added to `golem.css` (sticky sidebars, `@media (max-width: 1100px)` collapse to one column).
- [x] **B0a-6** — 7 tests in `tests/test_plugin_apidoc.py`: sidebar emission + rendered `sidebarblock sidebar-column`, `DescriptionList` for params, `Admonition` for raises, inline markup preservation, and sub-heading survival.
- [x] **B0a-7** — `ruff check src tests` + `ruff format --check` clean; `mypy --strict` clean on `api.py`.
- [x] **B0a-8 (session 2)** — Split-row wrapper: example-bearing docstrings emit `Open(role="split-row")` > `Open(role="prose-column")` + sidebars, with `.split-row > .content { display: contents }` so the two columns are the grid items. Without it the sidebars rendered as full-width sticky blocks under the prose.

**B0b — prose sidebars: N/A**. Verified upstream `asciidoctrine` already maps the `****` delimiter to a `sidebar` node, and `asciidoctype`'s `sidebar.html` renders it as `.sidebarblock`. No workaround needed.
   - Remaining upstream gap: `[sidebar]` on `====` delimiters yields an `example` node with `style=sidebar` instead of a `sidebar` node. Tracked as a tripwire.

**Upstream deficiencies found while implementing** — see `.kilo/plans/upstream-issues.md` for the issue text, and `tests/test_upstream_tripwires.py` (strict `xfail`) for the tripwires that flip the workarves off once fixed:
   - `asciidoctrine`: `[sidebar]` on `====` is not translated to a `Sidebar` node (only `****` is).
   - `asciidoctype`: `listing.html` ignores `role`, so a source block cannot be restyled through a role.

#### B1: Sticky Right Sidebar (TOC) — DONE (`7dc932f`)

**Verified gap:** `#golem-sidebar-right` (`golem.css:1631-1637`) sets `width`,
`padding`, `border-left`, `font-family`, `flex-shrink` but **no `position: sticky`**,
so the TOC scrolls away. `#golem-sidebar-left` already has it.

1. Add `position: sticky; top: 4.5rem; height: calc(100vh - 4.5rem); overflow-y: auto; align-self: start` to `#golem-sidebar-right`
2. The `4.5rem` accounts for header height (~3.5rem header + ~1rem padding from existing CSS)
3. Test: verify via `test_design_tokens.py` pattern checking for `position: sticky` in `#golem-sidebar-right`

> **As implemented:** `#golem-header` is not sticky, so the TOC pins to `top: 0`
> with `height: 100vh` and `align-self: flex-start` (sticky needs the flex item to
> stop stretching). A parity test locks the TOC and content-sidebar offsets equal.

#### B2′: API Page Sidebar Alignment — DONE (see B2′ note in status)

1. Measure actual `#golem-header` height: `padding: var(--space-md) var(--space-lg)` = `1rem 1.5rem`, plus h1 font-size `1.35rem` → total ~3.5rem
2. Set `#golem-sidebar-right` `top` to match header height + small gap (~4.5rem)
3. For API pages, `.class-multi-grid .sidebar-column` gets `position: sticky; top: 2.5rem` to align with the class header

> **Resolution:** the reference's `3.5rem`/`4.5rem` values assume a sticky global
> nav. Golem's header scrolls away, so pinning to the viewport top (`top: 0`) on
> both sticky panels is the self-consistent choice; the parity test enforces it.

#### B3: Uniform Heading Size on API Pages — DONE

**Verified gap:** `.class-multi-grid` has **0 rules in `golem.css`**. It is emitted by
`api.py:897` (`section.attributes["role"] = "class-multi-grid"`), and the apidoc
`section.html:7-8` folds the role into the CSS class, so the class reaches the HTML —
but nothing styles it.

1. Add `.class-multi-grid h2, .class-multi-grid h3, .class-multi-grid h4 { font-size: 1.35rem; font-weight: 700 }` to `golem.css`
2. This overrides per-level sizing only within `.class-multi-grid` containers, leaving prose headings (`golem.css:752-790`) untouched

> **As implemented:** the uniform rule must be scoped through `#golem-content`
> (`#golem-content .class-multi-grid h2/3/4`), because the per-level prose rules
> are id-scoped and a plain class selector would lose the cascade.

#### B4: Column Containment — DONE

**Verified gap:** `.prose-column` (5 hits) and `.doc-content-stream` (2 hits) are
emitted in HTML but have **0 rules in `golem.css`** — grid children have no
containment.

1. **Issue:** `.prose-column` and `.doc-content-stream` don't exist in the codebase yet. Verify in `skeleton.pt` — the main content is in `main#golem-content` with `<div tal:content="structure body_html" />`
2. Add `min-width: 0` to `main#golem-content` and to `.section-blocks` within `.class-multi-grid` to enable grid column containment
3. The `.class-multi-grid .adoc-section { display: contents }` (B11) handles the sub-grid aspect

> **As implemented:** `min-width: 0` on `#golem-content`, and `.prose-column` gets
> `min-width: 0` now that B0a-8 emits it. `.doc-content-stream` still does not
> exist; no rule until something emits it.

#### B5: Table Clipping/Overflow

> **Status: PENDING** — no overflow wrapper or test exists as of 2026-10-15.
> Implementation (a `table.html` override + `.table-scroll` CSS) is specified in
> `.kilo/plans/1792091844188-wave3-wave4-plan.md` Phase 1.

1. Add `overflow-x: auto; min-width: 0` wrapper for `.tableblock` containers
2. Column widths already handled by upstream `asciidoctype 0.1.0a7` `colgroup` (§2.3 verified)

#### B6: Sidebars Return to Main Column Below ~1180px — DONE (1100px, existing breakpoint)

1. Add `@media (max-width: 1180px) { .sidebar-column { position: static; width: 100%; } }`
2. **Risk:** 1180px is a 🎚 (lost constant). Start with 1100px (existing breakpoint) and adjust after measuring column widths.

> **As implemented:** 1100px (the existing breakpoint), alongside the `.split-row`
> one-column collapse.

#### B7: Collapsed Source Listings — DONE (`7dc932f`)

**Verified gap:** `details.source-drawer` (`golem.css:1293-1300`) has `overflow: hidden`
but **no `max-height` / `overflow-y`**, so an expanded drawer grows unbounded.
Tests at `test_design_tokens.py` verify the selector exists and uses tokens.

1. Add `details.source-drawer { max-height: 400px; overflow-y: auto }` when expanded
2. Test at `test_design_tokens.py:474` already verifies `details.source-drawer` exists and uses design tokens — need to add `max-height` + `overflow-y` assertions

#### B8: 4-State Non-Monotonic Nav Visibility Ladder — DONE

See Decision #2 above. Implementation is CSS-only.

> **As implemented:** exactly Decision #2 (768/992/1280). The previous monotonic
> `#golem-sidebar-right { display: none }` inside `@media (max-width: 1100px)` was
> removed. State 4 reuses State 3's selector so it wins on source order, not
> specificity. Tests assert the ladder, its `:has(.sidebar-column)` conditions, and
> that no visibility rule references the B10 position class.

#### B9: Nav Position — Adjacent by Default — DONE (default; no margin)

1. `#golem-wrapper` is `display: flex` (`golem.css:626-629`)
2. Add `margin-left: auto` to `#golem-sidebar-right` to push it to the right edge of the main content area, creating visual adjacency
3. Or use CSS Grid on `#golem-wrapper` for more control

> **As implemented:** see Decision #3. Adjacency is the natural flex default (the
> content's `max-width` leaves the free space to the *right* of the nav, so no
> auto margin is wanted); `margin-left: auto` is reserved for the opt-in class.

#### B10: Nav Helpers Flush-Right Config Flag — DONE

1. File: `src/golem/plugins/nav_helpers.py:223`
2. Add `flush_right_nav: bool = False` parameter to `NavigationHelpersPlugin.__init__`
3. Add to `from_config` method: `flush_right_nav = nav_cfg.get("flush_right_nav", False)`
4. Pass `nav_position: "flush-right"` to template context when enabled
5. File: `src/golem/templates/default/skeleton.pt:206` — add `tal:attributes="class 'golem-sidebar-right golem-toc' + (' nav-flush-right' if nav_position == 'flush-right' else '')"`
6. File: `src/golem/model/__init__.py:151-161` — add `nav_position: str | None` to `NavHelpersContext`
7. Test: `tests/test_plugin_nav_helpers.py` — verify `nav_position` in context when `flush_right_nav=True`

> **As implemented:** all seven steps. `templates.py` defaults `nav_position` to
> `None` in `template_kwargs` (matching the existing plugin-key pattern) so the
> template expression never sees an undefined name — a `| nothing` guard inside a
> `python:` expression breaks Chameleon's parser.

#### B11: Subgrid Fix — DONE (gate for B12/B13 and #21: now open)

1. Add to `golem.css`:
    ```css
    .class-multi-grid .adoc-section { display: contents }
    .class-multi-grid .section-blocks { display: contents }
    ```
2. **Rationale:** `section.html:8` injects `.section-blocks` div around child blocks, breaking CSS grid column inheritance under `.class-multi-grid`. `display: contents` makes the wrapper transparent to grid.

#### B12: Strip Non-Rail Left Borders — DONE

**Verified gap:** `.member-card` (emitted by `api.py:844`; the `.doc-rail` spellings
only exist in the hand-written mock, which is not a design target) has **0 rules in
`golem.css`**. The "keep only the rail border" audit couldn't run until B11 landed
and the rail became visible.

1. Audit all `border-left` rules in `golem.css` within `.doc-member` and `.member-card` contexts
2. Keep only `.doc-rail` border, remove others

> **As implemented:** the audit kept the `.doc-member` rail, the `.listingblock`/`pre`
> code accent (a global code affordance, not member clutter), the admonition colour
> rails (semantic), and the nav borders (page chrome). `.member-card` now wears the
> same `--border-rail` rail, and the standalone `.signature-container`'s
> `--color-primary` left accent is dropped inside cards so the rail is the only
> left border in a member hierarchy.

#### B13: Avoid Unnecessary Padding — DONE

1. Audit padding on `.class-multi-grid` children
2. Ensure no redundant padding is added

> **As implemented:** the cluster adds no padding at all; the only indent is the
> shared `--rail-indent` on `.member-card` (mirroring the approved `.doc-member`
> pattern). Tests assert no `padding` shorthand and no padding declarations on the
> grid wrappers.

### Wave 3 — #16 Design Tokens

1. Add `--badge-radius: var(--radius-full)` to `:root` (`golem.css:110-115` radius section)
2. Update `test_design_tokens.py` to assert `--badge-radius` exists
3. Close #16

### Wave 4 — Leaf Autodoc Features

| Issue | Task | Key Files | Notes |
|---|---|---|---|
| #19 | Glyph badge emission | `api.py` — emit `<span class="glyph-c">` on class signatures; `golem.css:1233+` already has `.glyph-*` classes | Need to add glyph emission to `_signature_listing()` or `_section()` |
| #23 | Signature block | Already done | `apidoc-signature.html`, `renderer.py:241`, `_tokenize_signature()` |
| #27 | Landmarks | Partially done | Add `aria-label="Table of contents"` to `#golem-sidebar-right`; skip-link already at `skeleton.pt:104` |
| #30 | kbd hint | JS + CSS | Add `keydown` handler in `skeleton.pt` `<script>` for `<kbd>t</kbd>` → toggle theme. Guard against `INPUT`/`TEXTAREA`/`SELECT`/`contentEditable` |
| #20 | Modifier pills | New CSS + ASG | `.modifier-pill` class with `--color-symbol-*` background |
| #24 | Source drawer | ASG emission | Wrap `apidoc-signature` in `<details class="source-drawer">` with `<summary>` |
| #28 | Heading hierarchy | Done | `ensure_absolute_levels` + `test_apidoc_headings.py` |

### Wave 5 — Structural Containment

| Issue | Task | Dependency |
|---|---|---|
| #21 | Member cards left rail | Requires B11 CSS (`display: contents`) — now landed |
| #17 | Tiered param disclosure | Requires #21; `format_class()` nested-class loop |

### Wave 6 — Interlinking

| Issue | Task | Dependency |
|---|---|---|
| #22 | Token interlinking | Requires Wave 5 |
| #18 | Returns/Raises popovers | Requires #22 |
| #25 | Type popovers | Widest fan-in, requires #22 |
| #31 | Intersphinx inventory | Requires #22 |

### Wave 7 — Composites

| Issue | Task | Dependency |
|---|---|---|
| #26 | Split-screen | Requires #21 + B1/B6 CSS — CSS side now landed |
| #29 | Member index | Requires #19 + #20 |

### Wave 8 — Independent / Housekeeping

| Issue | Task | Key Files |
|---|---|---|
| #2 | New theme/plugin scaffolding | `golem new` CLI command |
| #15 | Plugin ordering | `pyproject.toml` entry points |
| #35 | TemplateContext TypedDict | `model/__init__.py:192-218` |
| #34 | Aggregator page invalidation | `staleness.py` — template fingerprint check |
| #36 | Python-module DAG deps | `staleness.py` dependency graph |
| #6 | i18n/RTL | RFC (no implementation) |
| #8 | `golem ingest` | New CLI command |
| #38 | Asset cache-busting | `staleness.py` fingerprint |
| — | `release.yml` | `.github/workflows/release.yml` — copy from `deploy-docs.yml` |

## Testing Strategy (Red/Green TDD)

**Wave 2 tests:**
- `tests/test_plugin_apidoc.py::test_apidoc_docstring_examples_emit_sidebar` — B0a (verify `sidebarblock sidebar-column` in rendered HTML)
- `tests/test_plugin_apidoc.py::test_apidoc_docstring_params_render_description_list` — B0a (verify `DescriptionList` for parameters)
- `tests/test_plugin_apidoc.py::test_apidoc_docstring_returns_raises_render_admonition` — B0a (verify `Admonition` for raises/warns)
- `tests/test_plugin_nav_helpers.py::test_nav_flush_right_context` — B10
- `tests/test_design_tokens.py::test_badge_radius_token` — Wave 3
- `tests/test_design_tokens.py::test_sidebar_sticky_toc` — B1 (add to existing file)
- `tests/test_design_tokens.py::test_nav_visibility_4state_ladder` — B8 (CSS rule checks)

**Session 2 tests added:**
- `test_design_tokens.py::test_right_toc_sidebar_is_sticky` — B1
- `test_design_tokens.py::test_content_sidebar_and_right_toc_share_sticky_offset` — B1/B2′
- `test_design_tokens.py::test_class_multi_grid_subgrid_display_contents` — B11
- `test_design_tokens.py::test_class_multi_grid_uniform_heading_sizes` — B3
- `test_design_tokens.py::test_content_column_containment` — B4
- `test_design_tokens.py::test_sidebar_returns_to_main_column_when_narrow` — B6
- `test_design_tokens.py::test_member_card_keeps_only_rail_border` — B12
- `test_design_tokens.py::test_member_card_adds_no_box_padding` / `test_class_multi_grid_children_add_no_padding` — B13
- `test_design_tokens.py::test_split_row_grid_makes_columns_the_grid_items` — B0/B4
- `test_design_tokens.py::test_nav_visibility_4state_ladder` — B8
- `test_design_tokens.py::test_nav_position_adjacent_by_default_with_flush_right_opt_in` — B9/B10
- `test_plugin_apidoc.py::test_apidoc_docstring_without_examples_has_no_split_row` — B0a-8
- `test_plugin_nav_helpers.py::test_flush_right_nav_*` — B10

**Wave 4 tests:**
- `tests/test_plugin_apidoc.py::test_apidoc_renders_glyph_badges` — #19
- `tests/test_plugin_apidoc.py::test_apidoc_source_drawer` — #24

**Lint/typecheck:**
```
ruff check src tests
mypy src/golem
```

## Risks & Open Questions

1. **Docstring pipeline refactor scope:** Replacing `_docstring_nodes()` with direct construction touches all API node builders (`_function_node`, `_attribute_node`, `_class_node`, `_module_nodes`). Must run full test suite after each section-kind builder is added. Mitigation: add builders incrementally, start with examples (B0a-2), then params, then returns/raises.
2. **CSS `:has()` browser support:** `:has()` is supported in all modern browsers (Chromium 105+, Firefox 121+, Safari 15.4+). Golem targets modern browsers only — verified by existing `:has()` usage for tab panes in `golem.css:1109-1139`.
3. **B8 breakpoint values:** The 1180px value is a 🎚 (lost constant). Start with 1100px (matching existing breakpoint) and measure column widths during implementation.
4. **`display: contents` accessibility:** B11's `display: contents` on `.adoc-section` removes the `<section>` element from the accessibility tree. Verify with `role="region"` or `aria-labelledby` if accessibility tests fail. The plan pre-approved this approach from #26's review comment.
5. **`--bg-surface-subtle` inconsistency:** CSS defines `--bg-surface-subtle: var(--palette-neutral-50)` (line 131) which is the same as `--bg-canvas` (line 129). This is a pre-existing issue, not part of this plan's scope.
6. **`format_docstring()` retention:** Still used by `_signature_listing()` for signature formatting. Must NOT be used for docstring body rendering. Clear separation: signatures → `format_docstring()`; docstring bodies → `_docstring_nodes_direct()`.
7. **Griffe section kind coverage:** Some section kinds (`functions`, `classes`, `modules`, `type_aliases`, `type_parameters`) may not appear in typical docstrings. Implement as `Paragraph` fallback initially; enhance if needed.
8. **Ladder vs. stack window (open):** State 2 shows the nav at ≥768px while `#golem-wrapper` stays column-stacked until 801px (`max-width: 800px` query). In that 768–800px window the TOC renders as a stacked block after the content. Acceptable, but measure during browser QA; if undesirable, raise BP_nav to 801px.
9. **Split-row column width:** `.split-row` uses a fixed `320px` second column. At content widths below ~1100px the media query collapses it. Re-measure if prose columns read much narrower than 65–75ch with a sidebar present (RECONSTRUCTION §4.1 State 4 check).
