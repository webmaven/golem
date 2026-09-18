# SDD Progress Ledger - Wave 2

Plan: `/Users/michaelbernstein/.gemini/antigravity/brain/793c21ef-5b8d-4001-adf9-e5d28029e77a/implementation_plan.md`
Initial Base: `56d66e26ca25d71de1b6c5e3720234801176f870`

- [x] Task 1: `on_template_context` Build Hook (Issue #13)
- [x] Task 2: CSS Extraction & METAL Macro Slots in `skeleton.pt` (Issue #12 & #16)
- [x] Task 3: Typed ASG Domain Models & Visitors (Issue #14)
- [x] Task 4: Complete AST-Level NodeTransformer Macro Splicing (Issue #10)
- [ ] Task 5: Canonical GitHub/GitLab Source Links Plugin (Issue #3)
- [ ] Task 6: Navigation Helpers Plugin (Issue #4)
- [ ] Task 7: Index & Glossary Compilation Plugins (Issue #5)
- [ ] Task 8: `golem ingest` External Source Conversion CLI (Issue #8) - DEFERRED

## Wave 2 — Plan: `/Users/michaelbernstein/.gemini/antigravity/brain/793c21ef-5b8d-4001-adf9-e5d28029e77a/implementation_plan.md`
Initial Base: `56d66e26ca25d71de1b6c5e3720234801176f870`

- [x] Task 1: `on_template_context` Build Hook (commits 56d66e2..11328ee, review clean)
  Important: Pluggy LIFO dispatch means pipelined plugin context mutations (B reading A's output) require sequential hookimpl iteration — additive mutations work fine today.
  Minor: `extra_context`-key dict unwrap shim in templates.py:180-181 could mishandle a template variable literally named `extra_context`.
- [x] Task 2: CSS Extraction & METAL Macro Slots (commits 11328ee..c98762b, review clean)
- [x] Task 1 fixes: sequential dispatch + remove extra_context shim (commit f7c91f3, re-review clean)
- [x] Task 3 (Revised): Typed ASG Pipeline via `asciidoctrine.nodes` (commits 321e6de..020b841, review clean)
  Key outcome: No duplicate dataclass hierarchy created. Thin shim `golem.model` re-exports Node, AsgVisitor, AsgTransformer from `asciidoctrine.nodes`. Engine calls `resolve_to_ast`.
- [x] Task 1 Minor Fix: Unify `_invoke_asg_hook` and `_invoke_template_context_hook` into `_invoke_doc_hook` (commit b35e76f, review clean)
- [x] Task 4: AST-Level NodeTransformer Macro Splicing (commit f227830, review clean)
  Key outcome: Syntax updated to `golem.apidoc::target[...]` (dot-separated block macro), parsing into `BlockNode(name='golem.apidoc')`. Deprecated `on_pre_parse` and untyped dict helpers completely removed. `AsciiDocApi.get_asg_nodes` returns typed `list[Node]`. Upstream issue filed: webmaven/asciidoctrine#132.

