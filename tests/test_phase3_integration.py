import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any, List

from agenticx.llms.base import BaseLLMProvider
from agenticx.knowledge.base import BaseKnowledge
from agenticx.memory.core_memory import CoreMemory
from agenticx.brain.manager import BrainManager

from flows.basic_flow import BasicResearchFlow
from flows.advanced_flow import AdvancedResearchFlow
from models import ResearchReport, ReportSection

class TestPhase3Integration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Mock LLM Provider
        self.mock_llm = MagicMock(spec=BaseLLMProvider)
        self.mock_llm.ainvoke = AsyncMock(return_value="Mocked LLM Response")
        
        # Mock Search Tools
        self.mock_search_tool = MagicMock()
        self.mock_search_tool.to_openai_schema.return_value = {}
        self.mock_search_tool.arun = AsyncMock(return_value=[{"title": "Result", "url": "http://test.com", "snippet": "Test snippet"}])
        
        # Mock Knowledge Base
        self.mock_kb = MagicMock(spec=BaseKnowledge)
        self.mock_kb.add_text = AsyncMock()
        self.mock_kb.add_graph = AsyncMock()
        
        # Mock Memory
        self.mock_memory = MagicMock(spec=CoreMemory)
        self.mock_memory.add = AsyncMock()
        self.mock_memory.update_agent_state = AsyncMock()
        
        # Mock Brain Manager & Runtime
        self.mock_brain_manager = MagicMock(spec=BrainManager)
        self.mock_brain_runtime = MagicMock()
        self.mock_brain_runtime.search = AsyncMock(return_value=MagicMock(hits=[MagicMock(content="Brain knowledge")]))
        self.mock_brain_manager.get_runtime.return_value = self.mock_brain_runtime
        
        # Mock Agents
        self.mock_report = ResearchReport(
            title="Test Report",
            abstract="Abstract",
            sections=[ReportSection(title="Section 1", content="Content")]
        )

    @patch("flows.basic_flow.QueryGeneratorAgent")
    @patch("flows.basic_flow.ResearchSummarizerAgent")
    @patch("flows.basic_flow.ReportWriterAgent")
    async def test_basic_flow_with_kb_and_memory(self, mock_writer_cls, mock_summarizer_cls, mock_query_gen_cls):
        # Setup mocks
        mock_query_gen = mock_query_gen_cls.return_value
        mock_query_gen.generate_queries = AsyncMock(return_value=[])
        
        mock_summarizer = mock_summarizer_cls.return_value
        mock_summarizer.search_and_summarize = AsyncMock(return_value="Summary")
        
        mock_writer = mock_writer_cls.return_value
        mock_writer.generate_report = AsyncMock(return_value=self.mock_report)
        
        # Initialize Flow
        flow = BasicResearchFlow(
            llm_provider=self.mock_llm,
            search_tools=[self.mock_search_tool],
            knowledge_base=self.mock_kb,
            memory=self.mock_memory
        )
        
        # Execute
        await flow.kickoff_async(inputs={"topic": "AI", "objective": "Learn"})
        
        # Verify
        self.assertIn("Test Report", flow.state.final_report)
        self.mock_kb.add_text.assert_called()
        self.mock_memory.add.assert_called()
        self.mock_memory.update_agent_state.assert_called()

    @patch("flows.advanced_flow.QueryGeneratorAgent")
    @patch("flows.advanced_flow.ResearchSummarizerAgent")
    @patch("flows.advanced_flow.ReportWriterAgent")
    @patch("flows.advanced_flow.AdaptivePlanner")
    @patch("flows.advanced_flow.BrainManager")
    @patch("flows.advanced_flow.GraphBuilder")
    async def test_advanced_flow_with_multi_brain_and_graph(
        self, mock_graph_builder_cls, mock_brain_manager_cls, mock_planner_cls, 
        mock_writer_cls, mock_summarizer_cls, mock_query_gen_cls
    ):
        # Setup mocks
        mock_brain_manager_cls.instance.return_value = self.mock_brain_manager
        
        mock_planner = mock_planner_cls.return_value
        mock_plan = MagicMock()
        mock_plan.stages = [MagicMock()]
        mock_plan.current_stage = MagicMock()
        mock_plan.current_stage.get_pending_subtasks.return_value = []
        mock_plan.is_completed = True
        mock_planner.generate_initial_plan = AsyncMock(return_value=mock_plan)
        mock_planner.propose_plan_patch = AsyncMock(return_value=None)
        
        mock_query_gen = mock_query_gen_cls.return_value
        mock_query_gen.generate_queries = AsyncMock(return_value=[])
        
        mock_summarizer = mock_summarizer_cls.return_value
        mock_summarizer.search_and_summarize = AsyncMock(return_value="Summary")
        mock_summarizer.reflect = AsyncMock(return_value={"completeness_score": 1.0})
        
        mock_writer = mock_writer_cls.return_value
        mock_writer.generate_report = AsyncMock(return_value=self.mock_report)
        
        mock_graph_builder = mock_graph_builder_cls.return_value
        mock_graph_data = MagicMock()
        mock_graph_data.entities = [1, 2, 3]
        mock_graph_builder.build_from_text = AsyncMock(return_value=mock_graph_data)
        
        # Initialize Flow
        flow = AdvancedResearchFlow(
            llm_provider=self.mock_llm,
            search_tools=[self.mock_search_tool],
            knowledge_base=self.mock_kb,
            memory=self.mock_memory,
            mounted_brains=["brain_1"]
        )
        
        # Execute
        await flow.kickoff_async(inputs={"topic": "Deep Learning", "objective": "Research"})
        
        # Verify
        self.assertIn("Test Report", flow.state.final_report)
        self.mock_brain_manager.get_runtime.assert_called_with("brain_1")
        self.mock_kb.add_graph.assert_called()
        self.mock_memory.add.assert_called()

if __name__ == "__main__":
    unittest.main()
