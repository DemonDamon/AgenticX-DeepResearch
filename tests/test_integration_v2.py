"""
AgenticX-DeepResearch v2 集成测试

验证重构后的工作流在 Mock 模式下能正常运行。
"""

import sys
import os
import asyncio
from pathlib import Path

# Setup paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
agx_root = project_root.parent / "AgenticX"
sys.path.insert(0, str(agx_root))

os.chdir(str(project_root))


def test_imports():
    """Test all module imports work correctly."""
    print("=" * 60)
    print("TEST: Module Imports")
    print("=" * 60)
    
    # Core AGX imports
    from agenticx.core.agent import Agent, AgentContext, AgentResult
    from agenticx.core.task import Task
    from agenticx.tools.base import BaseTool
    from agenticx.llms.base import BaseLLMProvider
    from agenticx.llms.kimi_provider import KimiProvider
    print("  ✓ AGX core imports OK")
    
    # Models
    from models import (
        SearchResult, ResearchContext, ResearchIteration, Citation,
        SearchEngine, ResearchPhase, SearchQuery, KnowledgeGap, KnowledgeItem
    )
    print("  ✓ Models imports OK")
    
    # Tools
    from tools import (
        BaseSearchTool, SearchInput, SearchResultItem, SearchResponse,
        BochaaIWebSearchTool, BingWebSearchTool, GoogleSearchTool,
        MockBingSearchTool, MockBochaaISearchTool, MockGoogleSearchTool
    )
    print("  ✓ Tools imports OK")
    
    # Agents
    from agents import (
        QueryGeneratorAgent, ResearchSummarizerAgent,
        PlannerAgent, ReportWriterAgent, SearchAnalyzerAgent
    )
    print("  ✓ Agents imports OK")
    
    # Workflows
    from workflows import UnifiedResearchWorkflow, WorkflowMode
    print("  ✓ Workflows imports OK")
    
    # Report
    from report import StructuredReportBuilderTask, CitationManagerTask, QualityAssessmentTask
    print("  ✓ Report imports OK")
    
    # Interactive
    from interactive import (
        InteractiveResearchInterface, ProgressTracker,
        RealTimeMonitor, UserFeedbackHandler
    )
    print("  ✓ Interactive imports OK")
    
    # Utils
    from utils import clean_input_text, load_config
    print("  ✓ Utils imports OK")
    
    print("\n  ✅ ALL IMPORTS PASSED\n")
    return True


def test_tool_instantiation():
    """Test search tool instantiation."""
    print("=" * 60)
    print("TEST: Tool Instantiation")
    print("=" * 60)
    
    from tools import MockBingSearchTool, MockBochaaISearchTool, MockGoogleSearchTool
    
    mock_bing = MockBingSearchTool()
    print(f"  ✓ MockBingSearchTool: name={mock_bing.name}")
    
    mock_bochaai = MockBochaaISearchTool()
    print(f"  ✓ MockBochaaISearchTool: name={mock_bochaai.name}")
    
    mock_google = MockGoogleSearchTool()
    print(f"  ✓ MockGoogleSearchTool: name={mock_google.name}")
    
    # Test mock search execution
    result = mock_bing.run(query="test query", max_results=5)
    assert isinstance(result, dict), "Search result should be a dict"
    assert "results" in result, "Search result should have 'results' key"
    assert len(result["results"]) > 0, "Search results should not be empty"
    print(f"  ✓ MockBingSearchTool.run() returned {len(result['results'])} results")
    
    print("\n  ✅ TOOL INSTANTIATION PASSED\n")
    return True


def test_agent_instantiation():
    """Test agent instantiation."""
    print("=" * 60)
    print("TEST: Agent Instantiation")
    print("=" * 60)
    
    from agenticx.llms.kimi_provider import KimiProvider
    from agents import (
        QueryGeneratorAgent, ResearchSummarizerAgent,
        PlannerAgent, ReportWriterAgent, SearchAnalyzerAgent
    )
    
    # Create a mock LLM provider
    provider = KimiProvider(model='test', api_key='test-key', base_url='http://localhost')
    
    qg = QueryGeneratorAgent(llm_provider=provider)
    print(f"  ✓ QueryGeneratorAgent: name={qg.name}, role={qg.role}")
    
    rs = ResearchSummarizerAgent(llm_provider=provider)
    print(f"  ✓ ResearchSummarizerAgent: name={rs.name}, role={rs.role}")
    
    pa = PlannerAgent(llm_provider=provider)
    print(f"  ✓ PlannerAgent: name={pa.name}, role={pa.role}")
    
    rw = ReportWriterAgent(llm_provider=provider)
    print(f"  ✓ ReportWriterAgent: name={rw.name}, role={rw.role}")
    
    sa = SearchAnalyzerAgent(llm_provider=provider)
    print(f"  ✓ SearchAnalyzerAgent: name={sa.name}, role={sa.role}")
    
    print("\n  ✅ AGENT INSTANTIATION PASSED\n")
    return True


def test_workflow_instantiation():
    """Test workflow instantiation with all modes."""
    print("=" * 60)
    print("TEST: Workflow Instantiation")
    print("=" * 60)
    
    from agenticx.llms.kimi_provider import KimiProvider
    from workflows import UnifiedResearchWorkflow, WorkflowMode
    
    provider = KimiProvider(model='test', api_key='test-key', base_url='http://localhost')
    
    for mode in WorkflowMode:
        workflow = UnifiedResearchWorkflow(
            llm_provider=provider,
            mode=mode,
            max_research_loops=3,
            search_engine='mock'
        )
        assert workflow.mode == mode
        assert workflow.max_research_loops == 3
        assert workflow.search_tool is not None
        print(f"  ✓ WorkflowMode.{mode.name}: search_tool={type(workflow.search_tool).__name__}")
    
    print("\n  ✅ WORKFLOW INSTANTIATION PASSED\n")
    return True


def test_models():
    """Test data model creation and validation."""
    print("=" * 60)
    print("TEST: Data Models")
    print("=" * 60)
    
    from models import (
        SearchResult, ResearchContext, ResearchIteration,
        Citation, SearchEngine, ResearchPhase, SearchQuery,
        KnowledgeGap, KnowledgeItem
    )
    
    # Test SearchResult
    sr = SearchResult(
        title="Test Result",
        url="https://example.com",
        snippet="This is a test snippet",
        source=SearchEngine.MOCK
    )
    assert sr.title == "Test Result"
    print(f"  ✓ SearchResult: title={sr.title}, source={sr.source}")
    
    # Test SearchQuery
    sq = SearchQuery(query="test query", purpose="testing")
    assert sq.query == "test query"
    print(f"  ✓ SearchQuery: query={sq.query}")
    
    # Test KnowledgeGap
    kg = KnowledgeGap(topic="AI", description="Missing info about X", priority=8)
    assert kg.priority == 8
    print(f"  ✓ KnowledgeGap: priority={kg.priority}")
    
    # Test ResearchIteration
    ri = ResearchIteration(
        iteration_id=1,
        queries=[sq],
        search_results=[sr],
        phase=ResearchPhase.SEARCH_EXECUTION
    )
    assert len(ri.search_results) == 1
    print(f"  ✓ ResearchIteration: id={ri.iteration_id}, results={len(ri.search_results)}")
    
    # Test ResearchContext
    rc = ResearchContext(
        research_topic="Test Topic",
        research_objective="Test Objective",
        iterations=[ri]
    )
    assert rc.research_topic == "Test Topic"
    all_results = rc.get_all_search_results()
    assert len(all_results) == 1
    print(f"  ✓ ResearchContext: topic={rc.research_topic}, total_results={len(all_results)}")
    
    # Test Citation
    citation = Citation(
        title="Test Paper",
        source_url="https://example.com/paper",
        authors=["Author A"]
    )
    formatted = citation.format_citation()
    assert "Test Paper" in formatted
    print(f"  ✓ Citation: formatted={formatted[:50]}...")
    
    print("\n  ✅ DATA MODELS PASSED\n")
    return True


def test_workflow_mock_execution():
    """Test workflow execution with mock search (no real API calls)."""
    print("=" * 60)
    print("TEST: Workflow Mock Execution")
    print("=" * 60)
    
    from agenticx.llms.kimi_provider import KimiProvider
    from workflows import UnifiedResearchWorkflow, WorkflowMode
    from unittest.mock import AsyncMock, MagicMock, patch
    
    provider = KimiProvider(model='test', api_key='test-key', base_url='http://localhost')
    
    workflow = UnifiedResearchWorkflow(
        llm_provider=provider,
        mode=WorkflowMode.BASIC,
        max_research_loops=1,
        search_engine='mock'
    )
    
    # Mock the LLM provider's ainvoke method using object.__setattr__
    async def mock_ainvoke(prompt, **kwargs):
        if "search" in prompt.lower() or "queries" in prompt.lower() or "查询" in prompt:
            mock_resp = MagicMock()
            mock_resp.content = '{"queries": ["test query 1", "test query 2"]}'
            return mock_resp
        elif "分析" in prompt or "analyze" in prompt.lower():
            mock_resp = MagicMock()
            mock_resp.content = '{"thinking": "Analysis complete", "insights": ["insight1"], "knowledge_gaps": []}'
            return mock_resp
        else:
            mock_resp = MagicMock()
            mock_resp.content = "This is a comprehensive research report about the topic."
            return mock_resp
    
    # Patch ainvoke using object.__setattr__ to bypass Pydantic
    object.__setattr__(workflow.llm_provider, 'ainvoke', mock_ainvoke)
    
    # Execute workflow
    print("  ● Running basic mode workflow with mock LLM...")
    result = workflow.execute("人工智能最新进展")
    
    assert isinstance(result, dict), "Result should be a dict"
    assert result.get("success") == True, f"Workflow should succeed, got: {result.get('error', 'unknown')}"
    assert "final_report" in result, "Result should contain final_report"
    assert "metrics" in result, "Result should contain metrics"
    
    metrics = result["metrics"]
    print(f"  ✓ Execution time: {metrics.get('execution_time', 0):.2f}s")
    print(f"  ✓ Search count: {metrics.get('search_count', 0)}")
    print(f"  ✓ Loop count: {metrics.get('loop_count', 0)}")
    print(f"  ✓ Success rate: {metrics.get('success_rate', 0):.2%}")
    print(f"  ✓ Report length: {len(result.get('final_report', ''))} chars")
    
    print("\n  ✅ WORKFLOW MOCK EXECUTION PASSED\n")
    return True


def run_all_tests():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("  AgenticX-DeepResearch v2 Integration Tests")
    print("=" * 60 + "\n")
    
    tests = [
        test_imports,
        test_tool_instantiation,
        test_agent_instantiation,
        test_workflow_instantiation,
        test_models,
        test_workflow_mock_execution,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n  ❌ FAILED: {test_func.__name__}")
            print(f"     Error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print("=" * 60 + "\n")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
