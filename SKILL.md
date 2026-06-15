---
name: agenticx-deep-research
description: "A deep research skill that performs multi-iteration web searches, analyzes content, and generates comprehensive structured reports with citations and knowledge graphs."
tags: [research, analysis, report, knowledge-graph, mcp, deep-dive]
version: "0.5.0"
author: "AgenticX Team"
---

# AgenticX Deep Research Skill

## When to use this service

Use this skill when the user needs:

- A comprehensive, multi-page research report on a complex topic (technology, market, academic, etc.)
- Deep insights gathered from multiple sources with cross-validation
- Structured output including executive summary, detailed analysis, and citations
- A knowledge graph derived from the research results
- Multi-round iterative research with adaptive planning

Do **not** use this skill for simple factual lookups (use basic search instead) or real-time data queries (use a dedicated data API).

## How to invoke

This service is accessible via the NEAR AI Agent Market proxy using the MCP (Model Context Protocol) standard.

### Structured query

```json
{
  "input": {
    "query": "Analyze the competitive landscape of decentralized AI agent markets in 2026",
    "mode": "advanced",
    "max_iterations": 5
  }
}
```

### Natural language query (Recommended)

Pass the research topic directly. The AgenticX adaptive planner will automatically decompose it into sub-queries and iterate until quality thresholds are met.

```json
{
  "input": {
    "query": "调研 2026 年去中心化 AI Agent 市场的发展趋势和主要竞争者"
  }
}
```

### Response format

The service returns a task ID immediately. Deep research typically takes 3–10 minutes.

```json
{
  "output": {
    "task_id": "uuid-string",
    "status": "processing",
    "message": "Research task started. Poll /api/research/task/{task_id}/status for completion."
  },
  "provider": "AgenticX Team",
  "source": "https://github.com/DemonDamon/AgenticX-DeepResearch"
}
```

### Polling for results

```bash
# Check task status
curl https://your-deployment-domain.com/api/research/task/{task_id}/status

# Get final report (when status is "completed")
curl https://your-deployment-domain.com/api/research/task/{task_id}/report
```

## Capabilities

| Capability | Description |
| :--- | :--- |
| Multi-iteration search | Performs up to 5 rounds of adaptive web searches |
| Adaptive planning | Uses AgenticX AdaptivePlanner to re-plan based on knowledge gaps |
| Multi-brain architecture | Coordinates specialized sub-agents for different research phases |
| Knowledge graph export | Outputs structured knowledge graph in GraphRAG format |
| Multimodal input | Accepts text, PDF, and image inputs |
| SSE streaming | Real-time progress updates via Server-Sent Events |
| A2A compatible | Discoverable via `/.well-known/agent.json` (Google A2A standard) |

## Pricing

- Model: `per_call`
- Price: ~0.5 NEAR per research task
- Settlement: After task completion and report delivery

## Service details

- **Service name**: AgenticX Deep Research Service
- **Category**: research
- **Tags**: research, analysis, deep-dive, report, knowledge-graph, mcp, agenticx
- **Response time**: Up to 600 seconds for complex topics
- **GitHub**: https://github.com/DemonDamon/AgenticX-DeepResearch
