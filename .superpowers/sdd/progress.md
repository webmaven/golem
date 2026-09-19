# SDD Progress Ledger - Wave 2 Technical Debt & Polish

Plan: `/Users/michaelbernstein/.gemini/antigravity/brain/2804b968-b270-45c1-914d-87873e724b99/implementation_plan.md`
Initial Base: `cc73fa91a12668e2a2ce58431b31f21687f6f73c`

- [x] Task 1: Bundled Plugin Entry Points & Packaging Registration (`pyproject.toml`) — commits cc73fa9..0a96fc1, review clean
  Minor: comment step numbering in `cli.py` (step 2 eliminated; renumber later)
- [x] Task 2: Standardized Plugin Base Class (`GolemPlugin`), `GolemConfig` Cleanup, and Uniform `get_plugin_manager` — commits 0a96fc1..3cad233, review clean
  Minor: in `tests/test_plugins.py`, rename `test_uniform_class_resolution_config_none` to `test_uniform_class_resolution_default_config`.
- [x] Task 3: Bundled Plugin Refactoring (`source_links`, `nav_helpers`, `index_glossary`), AST Simplification, and `IndexGlossaryPlugin` Removal — commit 16d9481, review clean
  Minor: in `IndexPlugin` and `GlossaryPlugin`, delegate `from_config` to `super().from_config(config)`.
- [x] Task 4: Template Metal Slot Comments & Documentation (`skeleton.pt`, `theme-development.adoc`, `plugin-system.adoc`, `docs/plugins/*.adoc`) — commits 16d9481..b85c166, review clean
- [x] Task 5: End-to-End Integration Verification, Test Suite Updates, and Quality Gates — commit 8b67ace, review clean
  Minor: in `BuildEngine`, add fallback to `doc_meta.get("page_role")`.
