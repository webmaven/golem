# SDD Progress Ledger — Golem Fix Plan (v0.1.0a2 Review Issues)
Plan: /Users/michaelbernstein/.gemini/antigravity/brain/2e93ef0f-1c7b-4abd-ba2e-15df42d733a1/implementation_plan.md
Branch: fix/v0.1.0a2-review-issues
Branch start (MERGE_BASE): 8f771e7

Tasks:
- Task 1.1: Fix five except A, B: occurrences — COMPLETE (commit 97a379f)
- Task 1.2: Add CI canary test — COMPLETE (commit e25b6b8)
- Task 2.1: Separate discovery from registration in get_plugin_manager() — COMPLETE (commit 852ce52)
- Task 2.2: Add error isolation and ordering-significance warning — COMPLETE (commit 0aee786)
- Task 2.3: Document new plugin architecture in GolemSpecs — COMPLETE (commit 5df3ce9)
- Task 3.1: Replace fcntl with filelock — COMPLETE (commit db79fff)
- Task 4.1: Deduplicate load_config() via normalizer helper — COMPLETE (commit dbcb89c)
- Task 4.2: Cache discover_navigation() within build_site() — COMPLETE (commit 6b25d50)
- Task 4.3: Fix os.PathLike type annotation on on_ast_created — COMPLETE (commit 1ee9722)
- Task 5.1: Fix --version to use runtime package metadata — COMPLETE (commit 4062719)
- Task 5.2: Fix hardcoded author name in golem init — PENDING
- Task 5.3: Add coverage and pytest-cov to dev dependencies — PENDING
- Task 5.4: Remove docs_crit_eval.md from repo — PENDING
- Task 5.5: Add CONTRIBUTING.adoc — PENDING
Task 1.2: complete (commits 97a379f..e25b6b8, review clean — AST/tokenize canary in tests/test_syntax_invariants.py)
Task 2.1: complete (commits e25b6b8..852ce52, review clean — two-pass discovery/registration in get_plugin_manager)
Task 2.2: complete (commits 852ce52..0aee786, review clean — hook error isolation, conflict warnings, ruff py312 target)
Task 2.3: complete (commits 0aee786..5df3ce9, review clean — GolemSpecs and get_plugin_manager docstrings)
Task 3.1: complete (commits 5df3ce9..db79fff, review clean — replaced fcntl with filelock)
Task 4.1: complete (commits db79fff..dbcb89c, review clean — deduplicated load_config via _extract_config_values)
Task 4.2: complete (commits dbcb89c..6b25d50, review clean — nav tree cached once per build_site cycle)
Task 4.3: complete (commits 6b25d50..1ee9722, review clean — on_ast_created os.PathLike annotation corrected to Any)
Task 5.1: complete (commits 1ee9722..4062719, review clean — --version dynamically resolved from package metadata)
