"""
Basic Research Flow (v2 - agenticx.flow Based)

基于 agenticx.flow 实现的线性研究工作流。
用于执行简单的、单次迭代的研究任务。
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from agenticx.flow.base import Flow
from agenticx.flow.decorators import start, listen
from agenticx.llms.base import BaseLLMProvider

from agents import (
    QueryGeneratorAgent,
    ResearchSummarizerAgent,
    ReportWriterAgent,
)
from models import ResearchContext, SearchQuery, SearchResult, ResearchIteration
from tools import BaseSearchTool

logger = logging.getLogger(__name__)


class ResearchState(BaseModel):
    """研究流状态模型"""
    topic: str = ""
    objective: str = ""
    context: ResearchContext = Field(default_factory=lambda: ResearchContext(research_topic="", research_objective=""))
    queries: List[SearchQuery] = Field(default_factory=list)
    results: List[SearchResult] = Field(default_factory=list)
    summaries: List[str] = Field(default_factory=list)
    final_report: str = ""
    error: Optional[str] = None


class BasicResearchFlow(Flow[ResearchState]):
    """基础研究工作流 (线性)
    
    流程：
    Generate Queries -> Search & Summarize -> Generate Final Report
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        search_tools: List[BaseSearchTool],
        **kwargs
    ):
        super().__init__(**kwargs)
        self.llm = llm_provider
        self.search_tools = search_tools
        
        # 初始化 Agents
        self.query_gen = QueryGeneratorAgent(llm_provider=self.llm)
        self.summarizer = ResearchSummarizerAgent(
            llm_provider=self.llm,
            search_tools=self.search_tools
        )
        self.report_writer = ReportWriterAgent(llm_provider=self.llm)

    @start()
    async def generate_initial_queries(self):
        """第一步：生成初始查询"""
        logger.info(f"Starting research on: {self.state.topic}")
        self.state.context.research_topic = self.state.topic
        self.state.context.research_objective = self.state.objective
        
        queries = await self.query_gen.generate_queries(
            research_topic=self.state.topic,
            research_context={},
            knowledge_gaps=[],
            iteration_number=1,
            max_queries=3
        )
        self.state.queries = queries
        logger.info(f"Generated {len(queries)} initial queries")

    @listen(generate_initial_queries)
    async def search_and_summarize(self):
        """第二步：执行搜索并总结"""
        iteration = ResearchIteration(iteration_id=1, queries=self.state.queries)
        
        for query in self.state.queries:
            logger.info(f"Executing search for: {query.query}")
            summary = await self.summarizer.search_and_summarize(
                query=query.query,
                research_topic=self.state.topic
            )
            self.state.summaries.append(summary)
            
        iteration.analysis_summary = "\n\n".join(self.state.summaries)
        self.state.context.add_iteration(iteration)
        logger.info("Search and summarization completed")

    @listen(search_and_summarize)
    async def write_report(self):
        """第三步：撰写最终报告"""
        logger.info("Generating final report...")
        
        # 汇总引用
        all_citations = []
        for it in self.state.context.iterations:
            for res in it.search_results:
                all_citations.append(f"[{res.title}]({res.url})")
        
        report_obj = await self.report_writer.generate_report(
            research_context=self.state.context
        )
        report = report_obj.to_markdown()
        self.state.final_report = report
        logger.info("Final report generated")
        return report
