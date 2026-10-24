# Archived Design Artifacts

This directory contains hand-written HTML research mocks that were previously
kept at the repo root or in `docs/examples/`. They are **not generated output**
and **not a design target** for golem's autodoc rendering.

## Files

### `autodoc_reference.html`

Byte-identical research mock of next-generation autodoc design principles
(Principles 1-7: structural containment, atomic AST tokens, glyph badges,
modifier pills, semantic left-rail, signature labels, skip link).

Originally duplicated at both `docs/examples/autodoc_reference.html` and
`design-docs/autodoc_reference.html`. The `docs/examples/` copy was deleted
and this copy was moved here on 2026-10-22 during technical debt cleanup.

**Do not use as a reference for generated output.** Nothing in golem emits
this markup. It is retained only as historical design research.

## Why archived

- No `.adoc` source; nothing generates it.
- Contains research annotations ("Principle N" callout boxes, annotation
  bar, research preview banner) that are not production UI.
- Duplicated byte-for-byte across two locations — a maintenance hazard.
- Referenced in plans only as historical context, not as an active target.
