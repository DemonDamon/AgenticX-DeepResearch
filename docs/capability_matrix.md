# AgenticX-DeepResearch Capability Matrix

Last updated: 2026-06-16

This matrix keeps the project honest after the Kimi gap audit.  A component is
marked **real** only when it is wired into a runtime path and covered by tests.

| Capability | Status | Runtime path | Test coverage | Notes |
|---|---|---|---|---|
| CLI research entrypoint | needs-fix | `main.py` | import smoke test pending | P0 fixed legacy search-tool aliases. |
| Basic Flow | real | `flows/basic_flow.py` | flow unit tests | Generates 10 queries and summarizes them concurrently. |
| Advanced Flow | partial | `flows/advanced_flow.py` | mocked integration tests | Uses AdaptivePlanner/GraphRAG interfaces, but real external dependencies still need production validation. |
| Search tools | real | `tools/*_search.py` | engine and mock tests | BochaAI/Bing/Google adapters share `BaseSearchTool`. |
| Full content fetching | partial | `tools/content_fetch.py`, `BaseSearchTool(fetch_content=True)` | unit tests | P0 Jina Reader compatible fetcher is implemented; layered fetch is P1. |
| Token budget management | partial | `token_budget.py` | unit tests | New code paths use token-aware truncation; older legacy paths still need migration. |
| Parallel search/summarization | partial | `flows/basic_flow.py`, `flows/advanced_flow.py` | flow unit tests | Query summaries now run concurrently; lower-level multi-engine aggregation is P1. |
| GraphRAG | partial | `flows/advanced_flow.py` | mocked tests only | Interface exists; needs real graph build/export validation before claiming production readiness. |
| CoreMemory | partial | flow optional dependency | mocked tests only | Optional hook exists; no default durable memory backend. |
| Multi-Brain | partial | `AdvancedResearchFlow` | mocked tests only | Depends on AgenticX BrainManager; no local production fixture. |
| Report generation | real | `agents/report_writer.py`, `report/` | unit/integration tests | Markdown report exists; HTML dual artifact is P1. |
| Citation quality assessment | partial | `report/citation_manager.py`, `report/quality_assessment.py` | limited tests | URL-level management exists; semantic citation verification is P1/P2. |
| FastAPI service | real | `server/api.py` | server/protocol tests | Async tasks and SSE endpoints exist. |
| A2A/MCP/NEAR adapter | real | `server/near_adapter.py` | protocol tests | Protocol surface exists; market registration/deployed validation is external. |
| Web UI | missing | none | none | Planned for P2 after SSE/API contracts stabilize. |
