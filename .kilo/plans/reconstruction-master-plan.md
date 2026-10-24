# Golem — Master Reconstruction & Execution Plan (consolidated)

> **Consolidated on 2026-10-22** from the plan material that previously lived in
> `.kilo/plans/`:
>
> - `RECONSTRUCTION.md`
> - `1792047062509-reconstruction-plan.md`
> - `1792091844188-wave3-wave4-plan.md`
> - `upstream-issues.md`
>
> This file is the **single up-to-date plan**. Nothing here trims completed work;
> completed sections are retained and annotated with their final state.

---

## 0. Provenance & how to read this plan

- **Baseline status at `HEAD` `b2279b5`** (2026-09-26), reconstructed from issue bodies,
  issue comments, `git` provenance, and the installed upstreams.
- **Execution resumed** on branch `reconstruction-plan` on 2026-10-12.
- **Consolidated** on 2026-10-22; branch HEAD is `1a1e2df` (`Fix CSS layout for API doc
  pages`, 2026-10-21), preceded by `a5a6c21` (`feat(layout): checkpoint heading markup,
  card borders, and layout-mock.html before faux-container refactor`, 2026-10-17).

| Pre-consolidation file | Role |
|---|---|
| `.kilo/plans/RECONSTRUCTION.md` | Master tracking doc: waves, divergences, caveats, performance notes. |
| `.kilo/plans/1792047062509-reconstruction-plan.md` | Status + implementation-task ledger (Waves 2–8). |
| `.kilo/plans/1792091844188-wave3-wave4-plan.md` | Continuation plan: Phases 0–5 (Session 2 checkpoint → E2E). |
| `.kilo/plans/upstream-issues.md` | Upstream issue texts + strict xfail tripwires. |

---

## 1. Current execution status (consolidated, 2026-10-22)

### 1.1 Branch & HEAD

- Branch: `reconstruction-plan`
- HEAD: `1a1e2df` — `Fix CSS layout for API doc pages` (2026-10-21)

### 1.2 Working-tree delta consolidated on 2026-10-22 (uncommitted at consolidation time)

- `.kilo/plans/*` — `.class-multi-grid` → `.doc-card` rename applied to the tracking docs.
- `design-docs/`, `docs/examples/`, repo root — hand-written mock `autodoc_reference.html` moved to `design-docs/archive/`.
- `docs/about/{changelog,security,code-of-conduct}.adoc` — wrapper `= Title` lines removed (doubled-header fix).
- `CHANGELOG.adoc` — duplicate `=== Fixed` under `== 0.1.0a3` removed; CSS/API Docs bullet merged into the surviving `=== Fixed` (doubled-header fix).
- `pyproject.toml` — `xfail_strict = true`.
- `src/golem/plugins/apidoc/*`, `src/golem/templates/default/static/css/golem.css`, `tests/*` — post-E2E follow-through.

### 1.3 Execution status by wave

- **Wave 1 — Detour A:** ✅ COMPLETE (A1 `a9b258f`; A2/A3/A5/A6 `1b4c4e8`; A3′ `8b17e0c`; A4 `7620215`).
- **Wave 2 — Detour B:** ✅ COMPLETE (B0a `7dc932f`; B0a-8/B3/B4/B6/B11/B12/B13 `03099f7`; B5 `d1b4e88`; B1/B2′/B7/B8/B9/B10 `7dc932f`).
- **Wave 3 — #16 design tokens:** ✅ DONE (`1189335`).
- **Wave 4 — leaf autodoc features:** ✅ DONE (#19 `d4381d4`; #20 `7d09334`; #23 `2fd0886`; #24 `79fe020`; #27 `2f8470a`; #28 verified; #30 `d8b596f`).
- **Waves 5–8:** ⏳ NOT STARTED.

### 1.4 Latest landed work (post-Wave-4 follow-through)

- **`1a1e2df` `Fix CSS layout for API doc pages`** (2026-10-21) — consolidated change:
  - `api.py`: `_split_row_nodes` → no-op (partitioning moved into the template); example sidebars → `sidebar-track`; Attributes + Submodules sections → `member-card`; class section → bare `cls.name` title with `doc-card` role.
  - `templates/html5/section.html`: `is_card` no longer special-cases `class-multi-grid`; introduces `doc-grid` / `prose-column` / `sidebar-track` / `sidebar-content` / `child-slot`; splits prose/child/trailing blocks.
  - `templates/default/section.html`: `<section>` class sourced from the node `role` attribute.
  - `skeleton.pt`: nav `<details>` no longer hard-coded `open`; auto-opens at ≥860px via `matchMedia`.
  - `golem.css`: new tokens (`--measure-min`, `--measure-max`, `--sidebar-w`, `--sticky-top`, `--doc-col`, `--doc-gap`); `#golem-content section:not(.doc-card) { max-width: var(--doc-col) }`; `.doc-card` / `.doc-grid` / `.prose-column` / `.sidebar-track` / `.sidebar-content` / `.member-card` rules; ≥1400px doc-grid overlay; TOC visibility tiers 3/4/5 (1080px / 1400px / 1720px); collapse ≤1399px; stack ≤859px.
  - `CHANGELOG.adoc`: new `=== Fixed` / `==== CSS / API Docs` + entry (later de-duplicated).
- **`a5a6c21`** (2026-10-17) — layout checkpoint: heading markup, card borders, `layout-mock.html`.

### 1.5 E2E & test state at consolidation

- **E2E:** `golem build --clean` — 62 pages, zero failures; clean-build time **measured 2026-10-15 at ~1150s**, down from ~1000s.
- **Suite at consolidation:** full `tests/` — **628 passed / 2 xfailed**; `ruff check` / `ruff format --check` clean; `mypy src tests` → only the pre-existing repo-wide `asciidoctype` missing-stubs errors.

---

## 2. Wave & task ledger (consolidated)

### Wave 1 — Detour A: typed ASG construction ✅ COMPLETE

| # | Task | State | Commit |
|---|---|---|---|
| A1 | Delete `formatter.py` AsciiDoc-string emission; build typed ASG in `api.py` | ✅ Green | `a9b258f` |
| A2 | `templates/html5/` Chameleon templates | ✅ Green | `1b4c4e8` |
| A3 | Register via `AsciiDoctypeRenderer.register_template_directory()` | ✅ Green | `1b4c4e8` |
| A3′ | Staleness tracker template search paths | ✅ Green | `8b17e0c` |
| A4 | Restore Class example | ✅ Green | `7620215` |
| A5 | Nest methods in classes | ✅ Green | `1b4c4e8` |
| A6 | Acceptance test | ✅ Green | `1b4c4e8` |

### Wave 2 — Detour B: layout ✅ COMPLETE

| # | Task | State | Commit |
|---|---|---|---|
| B0a | Docstring → typed example sidebars | ✅ DONE | `7dc932f` (+ B0a-8 `03099f7`) |
| B0b | Prose sidebars | N/A | — |
| B1 | Sticky TOC | ✅ | `7dc932f` |
| B2′ | API sidebar alignment | ✅ | `03099f7` |
| B3 | Uniform heading sizes | ✅ | `03099f7` |
| B4 | Column containment | ✅ | `03099f7` |
| B5 | Table clipping/overflow | ✅ `d1b4e88` | — |
| B6 | Sidebars return below breakpoint | ✅ | `03099f7` |
| B7 | Source drawer max-height | ✅ | `7dc932f` |
| B8 | 4-state nav visibility ladder | ✅ | `03099f7` |
| B9 | Nav position adjacent-by-default | ✅ | `03099f7` |
| B10 | `flush_right_nav` opt-in | ✅ | `03099f7` |
| B11 | `display: contents` subgrid | ✅ | `03099f7` |
| B12 | Strip non-rail left borders | ✅ | `03099f7` |
| B13 | Avoid unnecessary padding | ✅ | `03099f7` |

### Wave 3 — #16 design tokens ✅ DONE

- `--badge-radius: var(--radius-full)`, `--badge-font-size`, `--badge-font-weight` added to `:root` + dark overrides; consumed by `.symbol-glyph`; issue closed.

### Wave 4 — leaf autodoc features ✅ DONE

| Issue | Feature | Commit | Note |
|---|---|---|---|
| #19 | Glyph badges C/M/F/I/T/X/V | `d4381d4` | Alias-safe classification |
| #20 | Modifier pills | `7d09334` | `@property` intentionally unemitted (noted on #20) |
| #23 | Signature block | `2fd0886` | Class/attribute labels added via working-tree delta |
| #24 | Source drawer | `79fe020` | — |
| #27 | Landmarks | `2f8470a` | Scope narrowed |
| #28 | Heading hierarchy | verified | `ensure_absolute_levels` + tests |
| #30 | kbd hint | `d8b596f` | Scope extended (`t` only) |

### Waves 5–8 ⏳ NOT STARTED

- Wave 5: #21 (member cards/left rail) → #17 (tiered parameter disclosure).
- Wave 6: #22 (token interlinking) → #18/#25 (returns/raises, type popovers) → #31 (intersphinx).
- Wave 7: #26 (split-screen) → #29 (member index).
- Wave 8: #15, #35, #34, #36, #6, #8, #38 (housekeeping backlog; #2 closed).

---

## 3. Resolved design decisions (consolidated)

1. **B0a:** docstring pipeline rewritten on `asciidocstring` (typed ASG; no Griffe-string reparse).
2. **B8:** 4-state nav visibility — CSS-only via `:has()`; ladder revised during `1a1e2df` to 1080px / 1400px / 1720px.
3. **B9/B10:** nav position adjacent-by-default; `flush_right_nav` opt-in.
4. **`--badge-radius: var(--radius-full)`.**

---

## 4. Documented divergences (consolidated)

- **§5.1 #4:** graph navigation deferred (breadcrumbs + `nav_tree_flat` only).
- **§5.2 #5:** in-body hover popovers deferred.
- **§5.3 #10:** macro syntax changed to `golem.apidoc::target[...]`.
- **§5.4 #14:** typed domain models rejected for a thin shim.
- **§5.5 #27:** scope narrowed (no explicit landmark roles).
- **§5.6 #30:** scope extended (only `t`).
- **§5.7 #26:** two pre-approved CSS resolutions (subgrid, conditional columns).
- **§5.9:** parser-bound performance; caching notes are pointers only.

---

## 5. Upstream issues (consolidated)

1. asciidoctrine — `[sidebar]` on `====` → `example`, not `sidebar`.
2. asciidoctype — `listing.html` ignores `role`.

Both covered by strict `xfail` tripwires in `tests/test_upstream_tripwires.py`; texts in `.kilo/plans/upstream-issues.md`.

---

## 6. Testing strategy & current verification state (consolidated)

- Strict Red/Green TDD throughout.
- Relevant tests: `tests/test_design_tokens.py`, `tests/test_plugin_apidoc.py`, `tests/test_upstream_tripwires.py`.
- **Consolidated finding:** `tests/test_plugin_apidoc.py::test_modifier_pills_render_after_heading` currently **fails** — its `make`/`__init__` assertions predate the glyph `title="..."` attribute addition and use a stale `<h3>` heading expectation.
- Three-file tally at consolidation: **1 failed, 92 passed, 2 xfailed**. Full-suite baseline: **628 passed / 2 xfailed**.

---

## 7. Risks & open questions (consolidated)

1. Docstring pipeline refactor scope.
2. CSS `:has()` browser support.
3. B8 breakpoint values.
4. `display: contents` accessibility.
5. `--bg-surface-subtle` inconsistency.
6. `format_docstring()` retention.
7. Griffe section-kind coverage.
8. Ladder vs. stack window; split-row column width.

---

## 8. Caveats (consolidated)

1. Static verification anchored at `HEAD` `b2279b5`.
2. Earlier `golem build --clean` producing zero HTML.
3. Absence-of-trace ≠ never-done.
4. 🎚 items: behavior specified, constants lost.
5. Small in-flight decisions with no traces.

---

## 9. Hand-off notes (consolidated)

- Next increment: **Wave 5** (#21 → #17), after the post-`1a1e2df` layout delta settles.
- Tracking issues to keep current: #16, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #34, #35, #36, #37, #38, #2, #6, #8, #15, #17, #18.

---

*End of consolidated master plan. Pre-consolidation plan files remain in `.kilo/plans/` for history.*
