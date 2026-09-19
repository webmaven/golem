# Subagent Model Selection & Thinking Level Guidelines

This rule establishes the model selection matrix and thinking level allocations for all subagent-driven development (SDD) tasks in this workspace.

---

## 1. Gemini Model Hierarchy & Roles

| Role | Target Model | Thinking Level | Rationale |
|---|---|---|---|
| **Trivial mechanical task** (exact snippet given, pure file write) | `gemini-3.5-flash-lite` | `LOW` | Lowest token cost, fast execution. |
| **Log triage / context scouting** (scanning large logs/codebase) | `gemini-3.5-flash-lite` | `LOW` | Ultra-high throughput (350–450 tps) and cheap ($0.30/1M) context ingest. |
| **Standard Task Implementer** (TDD, multi-file code diffs, debugging) | `gemini-3.7-flash` | `MEDIUM` | Premier coding workhorse (DeepSWE 65.3%), fast TDD iteration, surgical diffs. |
| **Complex Architectural Implementer** (refactoring interfaces, concurrency) | `gemini-3.7-flash` | `HIGH` | Deep deliberation on downstream effects. |
| **Per-Task Reviewer (Standard diffs)** | `gemini-3.7-flash` | `LOW` | Fast, cost-efficient spec & quality verification for well-defined diffs. |
| **Per-Task Reviewer (Complex logic/API change)** | `gemini-3.7-flash` | `MEDIUM` | Deeper deliberation on semantic invariants, interface contracts, and edge cases. |
| **Orchestrator: Plan Formulation** | `gemini-3.7-flash` | `MEDIUM` or `HIGH` | System topology planning, task decomposition, and architectural design. |
| **Orchestrator: Execution Dispatch** | `gemini-3.7-flash` | `LOW` (rarely `MEDIUM`) | Dispatching subagents, tracking test checkpoints, updating progress ledgers. |
| **Final Whole-Branch Reviewer** | `gemini-3.7-flash` | `HIGH` | Holistic repo verification, anti-pattern audit, guardrail enforcement. |
| **Second Opinion Reviewer** (Dissenting/Concurring) | `gemini-3.1-pro-preview` | `HIGH` | Reserved for complex multi-domain ambiguity or high-stakes second opinions. |

---

## 2. SDD Dispatch Invariants

1. **Never use `Model: "inherit"`:** Always explicitly designate the subagent model to prevent context bloating and rate limit exhaustion.
2. **Explicit Thinking Level:** Always configure subagent prompts or agent harnesses with discrete thinking levels (`LOW`, `MEDIUM`, `HIGH`).
3. **Commit before termination:** Any agent session (orchestrator or subagent) that has modified working tree files **must** run `git add` and `git commit` before terminating. An uncommitted working tree is lost work — subsequent sessions or tree resets will silently destroy it. Even a `WIP:` prefixed commit is acceptable; lost edits are not.

<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->
