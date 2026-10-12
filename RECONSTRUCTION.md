# Golem — Reconstruction & Execution Plan (post data-loss)

Status of work as of HEAD `b2279b5` (2026-09-26), reconstructed from issue bodies,
issue comments, `git` provenance, and the `asciidoctype`/`asciidoctrine` upstreams.
Nothing here is implemented — this is the plan to resume from.

---

## 0. Provenance & how to trust this

- **Verified facts** come from: source at `HEAD`, `git log`/`merge-base` ancestry,
  issue bodies, issue *comments* (which often override the issue body — see §5),
  and the installed upstream packages.
- **Recoverable-but-unpushed** work (the lost week) is **not in this clone** by
  construction: the only history is `main` + `origin/main` and the reflog has a
  single `clone:` entry. Where a decision "isn't in the code," it may still have
  existed only in the working tree — treat absence-of-trace ≠ never-done.
- **Re-derive-from-scratch** items (marked 🎚) were real decisions whose exact
  values/choices were lost; the *behavior* is specified, the *constants* are not.

---

## 1. Confirmed-complete foundation — do not re-implement

All verified present at `HEAD`. Several carry documented divergences from the
original issue text (see §5); treat the comments as the spec of record.

| Issue | State | Note |
|---|---|---|
| #12 METAL template slots | ✅ | Six `define-slot`s; CSS extracted to `golem.css` |
| #13 `on_template_context` hook | ✅ | Hookspec + invocation; `PageContext`/`TemplateContext` |
| #14 typed ASG | ✅ | **Via thin shim**, not the original dataclasses — see §5.4 |
| #10 AST `NodeTransformer` macro splicing | ✅ | As `golem.apidoc::target[]` — see §5.3 |
| #9 init profiles | ✅ | `library`/`cli`/`paper`/`blog`, `--profile` |
| #11 build lifecycle hooks | ✅ | `on_build_start`/`on_build_finish`, `BuildResult` |
| #1 fine-grained cache invalidation | ✅ | `node_types`, `theme_templates`, `golem_mark_stale` |
| #3 source links | ✅ | Providers, SSH normalization, format templates |
| #4 nav helpers | ⚠️ | Breadcrumbs + `nav_tree_flat` only; **graph nav deferred** (§5.1) |
| #5 index & glossary | ⚠️ | Compilation done; **in-body hover popovers deferred** (§5.2) |
| #7 pure-CSS radio tabs | ✅ | `:checked` + `:has()` |

`#16` (CSS design tokens) is effectively present (`--color-primary`,
`--bg-surface*`, `--font-mono`, `--border-color`, `.glyph-*` all exist) yet the
issue is still OPEN and every dependent marks it "(resolved)." Finalize remaining
tokens (e.g. `--badge-radius`), tick acceptance criteria, and **close it** — a
bookkeeping gap, not real work.

---

## 2. In-flight architectural decisions (recovered)

These were made during the lost week and are the reason Detours A/B exist.

### 2.1 Apidoc rendering = ASG → template (not AsciiDoc → reparse)
The pipeline was being moved from "emit AsciiDoc, reparse to nodes" to
"**take ASG and render it with Chameleon templates**," keeping only lightweight
AsciiDoc *skeleton stubs* where rendered HTML is included. This was a real (if
modest) perf win.

### 2.2 Plugin template discovery → `register_template_directory()` (upstream)
Golem does **not** need its own registration protocol or a
`golem_template_directories()` hook. `asciidoctype 0.1.0a7` ships:

```
AsciiDoctypeRenderer.register_template_directory(path)      # classmethod
AsciiDoctypeRenderer.get_registered_template_directories()  # classmethod → list[Path]
_PLUGIN_TEMPLATE_DIRS                                        # class-level registry
```

and `__init__` already merges the registry **ahead of** custom paths and core
(`registry → custom → core`). So: **plugins call `register_template_directory()`
at import; the renderer resolves automatically.** The only Golem-side gap is the
staleness tracker (`staleness.py::_get_template_search_paths`, ~L216-258), which
must extend with `get_registered_template_directories()` — one line, closes the
incremental-rebuild half of #37.

> ⚠ `asciidoctype 0.1.0a7` is on PyPI (2026-09-12) but has **no GitHub Release**
> (releases stop at `v0.1.0a6`) and neither repo has release automation. PyPI is
> the release of record; tags/releases drift by one. Don't audit upstream via
> `gh release view` — you'll get the wrong version.

### 2.3 Table widths are already fixed upstream
`[cols="1,3,1"]` handling shipped in `asciidoctype 0.1.0a7` via `colgroup` +
`renderer.extract_col_widths()` (asciidoctype#3, closed). **Do not redo column
widths.** The Golem-side remainder is only clipping/overflow (§Detour B-B5).

---

## 3. Current-state evidence (why the detours exist)

- `src/golem/plugins/apidoc/core/formatter.py` (346 lines) still emits
  **AsciiDoc strings** and is the **sole content path**; imported at `api.py:13`.
- `api.py::get_asg_nodes()` does `render_symbol() → AsciiDoc str →
  ASGResolver().resolve_to_ast() → nodes` — the residual reparse to remove.
- `api.py` already imports `Admonition/Node/Paragraph/Text` and defines
  `ensure_absolute_levels(nodes, base_level=2)` — direct-ASG scaffolding exists
  but is only used for heading levels.
- `src/golem/plugins/apidoc/templates/` is **empty**; `register_template_directory`
  has **zero** call sites in `src/`.
- Exactly **one** `position: sticky` in all of `src/` (`#golem-sidebar-left`,
  `golem.css:659`). Absent: `.class-multi-grid`, `.member-card`, `.class-grid-row`,
  `.sidebar-column`, `.doc-rail`, `.ast-token`, sticky TOC column, `:has(`.
- `.glyph-*` badges exist in CSS (`.golem.css:1233+`) but **nothing emits them**
  (formatter emits AsciiDoc, not badge markup) — the "features not showing up"
  symptom.
- Breakpoints in use: `1100px` (hide right sidebar) and `800px` (stack, unstick).
  Right nav is currently **monotonic**: visible >1100px, hidden below.
---

## 4. The Plan — waves, in dependency order

Ordering follows the explicit `Requires`/`Prerequisites` blocks in the issue
bodies plus the two in-flight detours. **Do not start Wave 4+ until A and B are
done** — every downstream feature renders through the path they fix.

### Wave 1 — Detour A: finish the decommissioning *(in flight)*

| # | Task | Why / evidence |
|---|---|---|
| **A1** | Delete `formatter.py`'s AsciiDoc-string emission. Build typed ASG nodes directly in `api.py` from the Griffe object. Remove the `render_symbol() -> str` path; keep only AsciiDoc *skeleton stubs* where rendered HTML is included. Target: `Griffe → ASG → template` | §3; `api.py:13` imports formatter |
| **A2** | Create `src/golem/plugins/apidoc/templates/html5/` — the Chameleon templates (signature, member card, class, module) | directory empty; 0 registration calls |
| **A3** | Register them via `AsciiDoctypeRenderer.register_template_directory()` at plugin import | resolved decision, §2.2 — **no** Golem registration protocol, **no** `golem_template_directories()` hook |
| **A3′** | `staleness.py::_get_template_search_paths()` must extend with `AsciiDoctypeRenderer.get_registered_template_directories()` | closes incremental-rebuild half of **#37** |
| **A4** | Restore the **Class** example — absent in `main` and in the reference HTML | was inadvertently removed at some point |
| **A5** | Nest **Methods inside Classes** (`.class-multi-grid` / `.class-grid-row`) — reference HTML has them as flat sibling `.split-row`s | reference must be restructured, not just copied |
| **A6** | **Acceptance test:** generated HTML contains `.member-card`, `.class-multi-grid`, `.ast-token` | proves the untangling is done |

> **A4/A5 note:** `docs/examples/autodoc_reference.html` and
> `design-docs/autodoc_reference.html` are byte-identical duplicates of a
> **hand-written mock** (no `.adoc` source; nothing generates it). It is **not the
> design target** — we borrowed from it. Whatever regenerated it is lost work.

### Wave 2 — Detour B: layout *(in flight)*

> **Terminology hazard — "sidebar" means two different things.**
> Every one of the ~28 `sidebar` matches in `src/` at HEAD refers to **page chrome**:
> `#golem-sidebar-left` (site navigation) and `#golem-sidebar-right` (in-page TOC).
> Neither is a *content* sidebar. **Content sidebars — the illustrative/interactive
> column — do not exist in any form.** See B0.

#### What content sidebars are for

**Primary motivating target: <https://webmaven.github.io/wgsl-primer>** (long-form
prose). Sidebars exist to hold **illustrative code examples and interactive content
related to the surrounding prose**. That is the requirement to design against.

In apidoc pages they are emitted **most commonly for example code** — eventually
including interactive examples — but **anything illustrative** may go in a sidebar.

> The wgsl-primer layout is **not** a design target. It was whatever could be
> implemented with the existing templates without breaking them. Take the *content
> requirement* from it, not any layout value. Equally, the `420-480px` sidebar
> width in `#26`'s comment is a *proposal*, not a measurement.

| # | Task |
|---|---|
| **B0** | **Content sidebars have no emission path at all** — this is the real gate on B6-B10. Splits into **B0a** (apidoc: examples *derived* from docstrings, no authoring syntax) and **B0b** (prose: syntax undecided). See §4.0 / §4.0.1 |
| **B1** | Sticky right sidebar (TOC) — mirror `#golem-sidebar-left` (`golem.css:659`). Currently the only `sticky` in `src/` |
| **B2′** | **API pages:** sticky sidebars align with the **top of the header in the left column** (reference uses `top: 3.5rem` global-nav / `top: 4.5rem` sidebar-card) |
| **B3** | **Uniform heading sizes on API pages** — nesting already conveys hierarchy, so per-level size is redundant. **Prose pages keep variable sizes** (`golem.css:752-790`, four distinct `h1..h4` rules — do not touch) |
| **B4** | **Column containment** — classes/API objects and their headers stay inside their column (`min-width: 0` on `.prose-column`/`.doc-content-stream`) |
| **B5** | **Tables:** clipping/overflow only (`overflow-x: auto` wrapper + `min-width: 0`). **Column widths are already fixed upstream** (§2.3) — do not redo |
| **B6** | **Sidebars return to the main column when narrow** — `position: static` below ~1180px |
| **B7** | Collapsed-by-default source listings: reasonable **`max-height` + `overflow-y: auto` when expanded** |
| **B8** | **In-page nav visibility — 4-state non-monotonic ladder** (see §4.1) |
| **B9** | **Position default:** when the nav is visible and there are **no sidebars**, sit it **adjacent to the main column** (width permitting) rather than flush right, so the blank expanse is not wasted |
| **B10** | **New `nav_helpers` config flag to force flush-right** *whenever the nav is visible* — the escape hatch for mixed-layout sites where the adjacent↔flush-right flip is distracting. **Affects position only; never visibility** |
| **B11** | `.display: contents` on `.class-multi-grid .adoc-section` / `.section-blocks` — pre-approved subgrid fix from #26's review comment |
| **B12** | **Strip non-rail left borders** to reduce visual clutter; keep only `.doc-rail` |
| **B13** | **Do not re-introduce unnecessary padding** (avoid, not fix) |

#### 4.0 B0 — sidebars cannot currently be emitted (verified)

B6-B10 all presuppose a sidebar that renders. **None can.** Verified against
`asciidoctrine 0.2.0a8` and Golem `HEAD`:

| Probe | Parses to | Golem renderer handles? |
|---|---|---|
| `[sidebar]` `====` … `====` | `Example` `{style: 'sidebar'}` | ❌ no dispatch |
| `[.sidebar]` `****` … `****` | **`Sidebar`** `{role: 'sidebar'}` | ❌ no dispatch |
| `[.aside-col]` `--` … `--` | `Open` `{role: 'aside-col'}` | ❌ no dispatch |
| `[source,python,role=sidebar]` | `Listing` `{role: 'sidebar'}` | ❌ role never inspected for layout |

`.split-row`, `.prose-column`, `.sidebar-column`, `.doc-rail`, `.member-card`,
`.sticky-sidebar-card` are **all absent from `src/`** — they exist only in the
borrowed-from mock (`docs/examples/autodoc_reference.html`), which is not a target.

So B0 is four coupled pieces, all missing: **(1)** an authoring syntax, **(2)**
renderer dispatch for `Sidebar`/`Example`/`Open` (and a role→layout check),
**(3)** the `.split-row` layout template, **(4)** the CSS. Until B0 lands there is
nothing for B6-B10 to position.

#### 4.0.1 B0a — apidoc is the common case, and it needs no authoring syntax

> **This supersedes part of B0.** The four-piece framing above assumes an authoring
> syntax is required. For the **most common apidoc case it is not** — the sidebar is
> *derived*, not written.

**Any source listing extracted from within a docstring becomes an example tied to
its object** (class, method, or function) **on that page.** No AsciiDoc author
decides; the association is a consequence of where the listing was written. So for
apidoc, B0's piece (1) **disappears** — the trigger is Griffe's docstring
structure, not markup.

The dependency already models this. `asciidocstring.DocstringExample` (in
`0.1.0a11`) carries exactly the fields needed:

```python
content: str
language: str = "python"
line_number: int = 1
is_interactive: bool = False   # >>> prompts present
attributes: dict[str, Any]
```

**But Golem consumes none of it.** Verified: `asciidocstring` appears in exactly
**one** place in `src/` — `formatter.py`, and only at lines 6, 159, 162, 190 — via
`asciidocstring.griffe_bridge.to_asciidoc(sections)`. The string
`example`/`DocstringExample` has **zero** matches across
`src/golem/plugins/apidoc/` **and** `src/golem/plugins/doctest/`.

That is the crux: `format_docstring()` flattens the whole docstring to an
AsciiDoc **string**, so examples are no longer addressable objects by the time the
pipeline holds them. They cannot be moved to a sidebar because nothing knows which
block was an example, or which object it belonged to. **This is a second,
independent reason Detour A matters** — it is not only a performance win; the
docstring→AsciiDoc→reparse round-trip is what destroys the object/example
association the sidebar layout depends on.

So B0a is: keep `DocstringExample` instances typed end-to-end, tag each with its
enclosing Griffe object path, and emit them into the sidebar column rather than the
prose column. `is_interactive` is the hook for the future interactive examples.

**Prose trigger: undecided.** For long-form pages the in-prose trigger was never
settled; presumed similar. Note this makes B0's pieces (1)-(4) apply to prose only —
so B0 splits into **B0a** (apidoc: derived, needs no syntax) and **B0b** (prose:
needs the syntax decision above).

> **Two independent axes — do not couple them.**
> - **Visibility (B8)** — pure CSS in `golem.css`: breakpoint × sidebar-presence.
>   **Not flag-dependent, in any state.**
> - **Position (B9/B10)** — adjacent-by-default vs. forced flush-right. The **only**
>   flag-dependent axis and the **only** Python-side change (`nav_helpers.py` exposes
>   only `home_title`/`home_url` today); the flag must reach the template as a class
>   or attribute on the nav element so CSS can act on it.
>
> They share selectors, but the flag must **never** gate visibility, and no
> visibility change may reposition the nav.

#### 4.1 The B8 visibility ladder 🎚

Non-monotonic — appears, dips, reappears. Replaces today's monotonic rule
(`display:none` at 1100px):

```
State 1  — narrowest                          : HIDDEN
State 2  — ≥ BP_nav                           : APPEARS (position per B9/B10)
State 3  — ≥ BP_sticky, only IF sidebars exist: HIDDEN
State 4  — ≥ BP_wide                          : APPEARS, even with sidebars
```

- **CSS-only**, via `:has(.sidebar-column)`-style conditions — the nav stays in
  the DOM; visibility is breakpoint **and** sidebar-presence driven.
  **This ladder is entirely flag-independent.**
- **State 3 is conditional on sidebars.** A page with no sidebars goes straight
  State 2 → State 4 — no dip, since nothing competes for the right-hand space.
- **Position is a separate axis** (B9/B10). Appearing in State 2/4 means *visible*,
  not *adjacent* — where it sits is decided independently of whether it shows.
- **Breakpoint px values are lost** — re-derive against existing `1100px`/`800px`.
- **State 4 must be checked against four columns, not three.** At the widest
  breakpoint with sidebars present the layout carries: (1) left site nav,
  (2) main content, (3) in-page/API sidebar, (4) in-page nav. Verify the prose
  column still measures ~65–75ch. If it does not, dropping the left site nav to
  a drawer at that breakpoint is the honest trade — do not narrow the text
  column to keep all four.



### Wave 3 — #16 design tokens
Effectively complete. Tick acceptance criteria, add any missing token
(`--badge-radius`), **close it**. 12+ issues already cite it as "(resolved)."

### Wave 4 — leaf autodoc features (unblocked once A + B land)
`#19` glyph badges · `#23` signature block · `#27` landmarks *(narrowed — §5.5)* ·
`#30` kbd hint *(extended — §5.6)* · `#20` modifier pills · `#24` source drawer ·
`#28` heading hierarchy

### Wave 5 — #21 → #17
`#21` structural containment (member cards, left rail), then `#17` tiered
parameter disclosure — its nested-class `format_class()` loop prescribes
`.class-multi-grid` markup, so it **must follow #21**.

### Wave 6 — interlinking
`#22` atomic token interlinking → then `#18` Returns/Raises and `#25` type
popovers (widest fan-in), then `#31` Intersphinx inventory.

### Wave 7 — composites
`#26` split-screen (needs `#21` + B1/B6) · `#29` member index (needs `#19`+`#20`).

### Wave 8 — independent / housekeeping
`#2` new theme/plugin scaffolding · `#15` plugin ordering · `#35` `TemplateContext`
TypedDict · `#34` aggregator page invalidation · `#36` Python-module DAG deps ·
`#6` i18n/RTL (RFC) · `#8` `golem ingest` · `#38` asset cache-busting

**Also:** add a `release.yml` (tag → PyPI **and** GitHub Release) so tags/releases/
PyPI cannot drift again (§2.2 note). `deploy-docs.yml` is the pattern to copy.

---

## 5. Documented divergences — comments override issue bodies

Where an issue comment states the implementation differed from the original
request, **the comment is the spec of record.**

**5.1 #4 — graph navigation deferred.** Breadcrumbs + `nav_tree_flat` shipped;
"topic and dependency graph visualization" was intentionally omitted to keep nav
helpers lightweight. Docs cover only breadcrumbs/flat trees.

**5.2 #5 — in-body hover popovers deferred.** Index/glossary *compilation* done;
"live hover definitions / popover tooltips in body text" decoupled and deferred to
later frontend autodoc/popover work.

**5.3 #10 — macro syntax changed.** Planned `golem:apidoc[symbol]`; shipped
`golem.apidoc::target[...]` because AsciiDoctrine forbids `:` in macro names
(asciidoctrine#132). **Zero legacy shim** — `on_pre_parse` text-substitution was
removed outright, no deprecation period, per alpha DX policy.

**5.4 #14 — typed domain models rejected for a thin shim.** Original plan
(`GolemDocument`/`GolemSection`/`GolemBlock` + bespoke visitors) was implemented in
`f671826`, **reverted** by `321e6de` (~2,510 lines deleted), then re-landed as a
thin `golem.model` shim re-exporting asciidoctrine's `Node`/`NodeVisitor`/
`NodeTransformer` in `020b841`. Rationale: avoid duplicating ~2,000 lines upstream
already owns. The reverted work is recoverable via
`git show f671826:src/golem/model/asg.py`.

**5.5 #27 — scope narrowed.** Do **not** add explicit `role=` to
`<header>/<main>/<aside>/<footer>` — implicit ARIA roles are correct. Only: skip
link (`#golem-content`, class `.skip-link`) + `aria-label`s (e.g.
`aria-label="Table of contents"`).

**5.6 #30 — scope extended.** Add a `keydown` handler in `skeleton.pt`'s existing
inline `<script>` so the `<kbd class="kbd-shortcut">t</kbd>` hint actually fires
the theme toggle — guarded against `INPUT`/`TEXTAREA`/`SELECT`/`contentEditable`.

**5.7 #26 — two pre-approved CSS resolutions.**
- *Subgrid:* `.class-multi-grid .adoc-section { display: contents }` and
  `.class-multi-grid .section-blocks { display: contents }` (AsciiDoctype's
  `section.html` injects `.section-blocks`, breaking column inheritance). Option B
  (monolithic passthrough) was rejected — it would hide content from the ASG.
- *Conditional columns:* `.class-grid-row { grid-template-columns: minmax(0,1fr) }`
  by default, with `:has(.sidebar-column)` activating the two-column variant —
  so no blank reserved column when there are no examples.

---

## 6. Caveats

1. **All verification is static**, at `HEAD` `b2279b5`. The test suite was never
   run (missing deps at the time of first investigation; a venv now exists).
2. The earlier `golem build --clean` producing **zero HTML** is very likely
   Detour A's symptom — it is corroborating evidence, not a diagnosis.
3. **Absence-of-trace ≠ never-done** for anything unpushed. This clone has only
   `main` + `origin/main`; the reflog has a single `clone:` entry.
4. 🎚 items: behavior specified, **constants lost** and must be re-derived.
5. ~half-a-dozen small in-flight architectural decisions left no trace at all;
   the ones recovered are in §2. Add an ADR when you land the next one.
