import asyncio
import os
from unittest.mock import AsyncMock

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")

import pytest

from agents.query_generator import QueryGeneratorAgent
from flows.basic_flow import BasicResearchFlow, ResearchState
from tools.content_fetch import ContentFetchResult, JinaContentFetcher
from tools.base_search import SearchResultItem
from token_budget import TokenBudget


class DummyLLM:
    pass


def test_query_generator_fallback_produces_ten_diverse_queries():
    agent = QueryGeneratorAgent(llm_provider=None)

    queries = asyncio.run(
        agent.generate_queries(
            research_topic="AI Agent 市场分析",
            research_context={},
            knowledge_gaps=[],
            iteration_number=1,
            max_queries=10,
        )
    )

    assert len(queries) == 10
    assert len({q.query for q in queries}) == 10
    assert any("最新" in q.query or "2026" in q.query for q in queries)


def test_token_budget_truncates_by_token_budget_not_character_count():
    budget = TokenBudget(model_name="gpt-4o-mini", max_tokens=12)
    text = "人工智能 Agent 深度研究 " * 20

    truncated = budget.truncate(text)

    assert truncated
    assert budget.count(truncated) <= 12
    assert len(truncated) < len(text)


@pytest.mark.asyncio
async def test_jina_content_fetcher_builds_reader_url_and_normalizes_markdown():
    async def fake_get(url, **kwargs):
        class Response:
            status_code = 200
            text = "# Title\n\nUseful body"

            def raise_for_status(self):
                return None

        assert url == "https://r.jina.ai/http://example.com/article"
        return Response()

    fetcher = JinaContentFetcher(timeout=1)
    fetcher._client_get = fake_get

    result = await fetcher.fetch("http://example.com/article")

    assert result.ok is True
    assert result.url == "http://example.com/article"
    assert "Useful body" in result.content


@pytest.mark.asyncio
async def test_basic_flow_summarizes_queries_concurrently():
    state = ResearchState(topic="并行搜索测试", objective="验证并行")
    flow = BasicResearchFlow(llm_provider=DummyLLM(), search_tools=[], state=state)
    # Use SearchQuery-like objects without depending on the LLM.
    from models import SearchQuery

    state.queries = [SearchQuery(query="q1"), SearchQuery(query="q2"), SearchQuery(query="q3")]
    calls = []

    async def fake_summary(query, research_topic):
        calls.append(query)
        await asyncio.sleep(0.01)
        return f"summary:{query}"

    flow.summarizer.search_and_summarize = fake_summary

    await flow.search_and_summarize()

    assert sorted(calls) == ["q1", "q2", "q3"]
    assert sorted(state.summaries) == ["summary:q1", "summary:q2", "summary:q3"]
