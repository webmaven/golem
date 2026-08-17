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
