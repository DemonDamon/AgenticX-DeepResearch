import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

# 添加路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, '/home/ubuntu/AgenticX')

from flows import BasicResearchFlow, AdvancedResearchFlow, ResearchState
from models import SearchQuery, ResearchIteration
from agenticx.flow.execution_plan import ExecutionPlan, ExecutionStage, Subtask

async def test_basic_flow():
    print("\n--- Testing BasicResearchFlow ---")
    # Mock LLM and Tools
    mock_llm = MagicMock()
    mock_tool = MagicMock()
    
    # 模拟 QueryGeneratorAgent 的行为
    # 注意：在我们的实现中，Flow 内部会创建 Agent，所以我们需要 Mock 内部调用
    # 这里我们通过注入 Mock LLM 来间接控制
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"queries": [{"query": "test query", "reasoning": "test"}]}'))
    
    state = ResearchState(topic="AI", objective="Test AI")
    flow = BasicResearchFlow(llm_provider=mock_llm, search_tools=[mock_tool], state=state)
    
    # 强制注入 Mock 绕过 Pydantic 校验
    mock_gen = AsyncMock(return_value=[SearchQuery(query="test query", reasoning="test")])
    mock_sum = AsyncMock(return_value="This is a test summary.")
    mock_report = MagicMock()
    mock_report.to_markdown.return_value = "# Test Report\n\nSuccess."
    mock_rep = AsyncMock(return_value=mock_report)
    
    object.__setattr__(flow.query_gen, 'generate_queries', mock_gen)
    object.__setattr__(flow.summarizer, 'search_and_summarize', mock_sum)
    object.__setattr__(flow.report_writer, 'generate_report', mock_rep)
    
    report = await flow.kickoff_async()
    
    # 如果 kickoff_async 返回 None，尝试从 state 中获取
    if report is None:
        report = flow.state.final_report
        
    print(f"Report: {report[:50] if report else 'None'}...")
    assert "Test Report" in report
    assert len(state.summaries) == 1
    print("BasicResearchFlow test passed!")

async def test_advanced_flow():
    print("\n--- Testing AdvancedResearchFlow ---")
    mock_llm = MagicMock()
    mock_tool = MagicMock()
    
    state = ResearchState(topic="Deep Learning", objective="Deep Test")
    flow = AdvancedResearchFlow(llm_provider=mock_llm, search_tools=[mock_tool], max_iterations=2, state=state)
    
    # Mock Planner
    mock_plan = ExecutionPlan(goal="Test")
    mock_plan.add_stage(ExecutionStage(name="Stage 1", description="Test Stage"))
    mock_plan.stages[0].add_subtask(Subtask(name="Test Task", query="test subtask"))
    
    # 强制注入 Mock 绕过 Pydantic 校验
    mock_init_plan = AsyncMock(return_value=mock_plan)
    mock_patch = AsyncMock(return_value=None)
    mock_gen = AsyncMock(return_value=[SearchQuery(query="q1", reasoning="r1")])
    mock_sum = AsyncMock(return_value="Summary 1")
    mock_reflect = AsyncMock(return_value={"completeness_score": 0.9, "reflection_summary": "Good"})
    mock_report_adv = MagicMock()
    mock_report_adv.to_markdown.return_value = "# Advanced Report"
    mock_rep = AsyncMock(return_value=mock_report_adv)
    
    object.__setattr__(flow.planner, 'generate_initial_plan', mock_init_plan)
    object.__setattr__(flow.planner, 'propose_plan_patch', mock_patch)
    object.__setattr__(flow.query_gen, 'generate_queries', mock_gen)
    object.__setattr__(flow.summarizer, 'search_and_summarize', mock_sum)
    object.__setattr__(flow.summarizer, 'reflect', mock_reflect)
    object.__setattr__(flow.report_writer, 'generate_report', mock_rep)
    
    report = await flow.kickoff_async()
    
    if report is None:
        report = flow.state.final_report
        
    print(f"Report: {report}")
    assert "Advanced Report" in report
    assert state.context.current_iteration == 1 # 因为 completeness 0.9 > 0.8，一轮就结束了
    print("AdvancedResearchFlow test passed!")

if __name__ == "__main__":
    asyncio.run(test_basic_flow())
    asyncio.run(test_advanced_flow())
