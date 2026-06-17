---
name: Kimi Gap Closure TDD Roadmap
source: kimi_vs_agenticx.agent.final.md
created: 2026-06-16
method: spec coding / TDD
status: in-progress
---

# AgenticX-DeepResearch Kimi Gap Closure Plan

This plan turns the Kimi-vs-AgenticX audit into executable engineering phases.
Each phase must start with tests/specs, then implementation, then full regression.

## Phase P0: Blocking Capability Fixes (0-1 month)

Goal: make the current codebase honestly runnable and materially improve the
information intake ceiling.

Acceptance criteria:

- CLI/API imports work without broken symbol names.
- Search query generation defaults to 10 diverse queries for first-pass research.
- Basic and Advanced flows execute query summarization concurrently.
- Search results can be enriched with full page Markdown through Jina Reader style
  fetching, with timeouts and graceful failure.
- Token handling uses a token budget abstraction instead of raw `content[:1000]`
  slicing for new code paths.
- A capability matrix documents which advanced components are real, partial, or
  deferred.
- Tests cover the above without live network or paid LLM calls.

Deliverables:

- `tools/content_fetch.py`
- `utils/token_budget.py`
- P0 regression tests under `tests/`
- Updated exports and flow wiring
- `docs/capability_matrix.md`

## Phase P1: Competitive Core (1-3 months)

Goal: move from snippet-based research prototype to industrial-entry research
service.

Acceptance criteria:

- Layered fetcher supports HTTP fast path, HTML-to-Markdown service, and browser
  fallback behind a common interface.
- Query planner supports 20 iterative queries with gap-driven follow-ups.
- Citation verification checks URL reachability and content alignment.
- Observability exposes structured logs, Prometheus metrics, and circuit breaker
  states.
- Markdown reports also produce a styled HTML artifact with navigation and basic
  charts.

TDD specs:

- Fetcher routing tests for static, markdown-service, and browser-required pages.
- Citation verifier tests for reachable, unreachable, supported, and unsupported
  claims.
- Report renderer snapshot tests for Markdown and HTML.
- Metrics tests for task lifecycle, token counts, tool failures, and latency.

## Phase P2: Architecture Leap (3-6 months)

Goal: replace linear workflow limits with open, parallel, multi-agent orchestration.

Acceptance criteria:

- LangGraph-compatible core workflow reaches feature parity with current v2 flows.
- Supervisor-Worker architecture separates research, analysis, writing, and
  verification roles.
- Session memory and long-term vector memory are real runtime dependencies, not
  placeholder interfaces.
- Multi-layer citation verification includes paragraph alignment and optional
  LLM-as-a-Judge.
- Basic Web UI supports task submission, live SSE progress, report viewing, and
  history.

TDD specs:

- Workflow parity tests comparing v2 and LangGraph outputs on mock tasks.
- Supervisor routing tests with recursion limits and deterministic decisions.
- Memory persistence and retrieval tests.
- End-to-end UI/API contract tests.

## Phase P3: Middleware Strategy (6-12 months)

Goal: position AgenticX-DeepResearch as open deep-research middleware.

Acceptance criteria:

- A2A/MCP/NEAR connectors are factored into independently installable packages.
- LangGraph, CrewAI, and PydanticAI integrations expose deep research as a native
  node/tool/dependency.
- RL-enhanced decision modules are prototyped for query strategy and content
  quality ranking.
- Enterprise readiness plan covers audit logs, privacy controls, and compliance.

TDD specs:

- Connector package compatibility tests.
- Framework integration contract tests.
- Policy-module offline evaluation harness.
- Compliance/audit event schema tests.
