"""
Basic Research Flow (v2 - agenticx.flow Based)

基于 agenticx.flow 实现的线性研究工作流。
用于执行简单的、单次迭代的研究任务。
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict

from agenticx.flow.base import Flow
from agenticx.flow.decorators import start, listen
from agenticx.llms.base import BaseLLMProvider
from agenticx.knowledge.base import BaseKnowledge
from agenticx.memory.core_memory import CoreMemory

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
    model_config = ConfigDict(arbitrary_types_allowed=True)

    topic: str = ""
    objective: str = ""
    context: ResearchContext = Field(default_factory=lambda: ResearchContext(research_topic="", research_objective=""))
    queries: List[SearchQuery] = Field(default_factory=list)
    results: List[SearchResult] = Field(default_factory=list)
    summaries: List[str] = Field(default_factory=list)
    final_report: str = ""
    error: Optional[str] = None
    
    # 第三阶段引入：统一知识库和记忆接口
    knowledge_base: Optional[BaseKnowledge] = None
    memory: Optional[CoreMemory] = None


class BasicResearchFlow(Flow[ResearchState]):
    """基础研究工作流 (线性)
    
    流程：
    Generate Queries -> Search & Summarize -> Generate Final Report
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        search_tools: List[BaseSearchTool],
        knowledge_base: Optional[BaseKnowledge] = None,
        memory: Optional[CoreMemory] = None,
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
        
        # 注入知识库和记忆
        if knowledge_base:
            self.state.knowledge_base = knowledge_base
        if memory:
            self.state.memory = memory

    @start()
    async def generate_initial_queries(self):
        """第一步：生成初始查询"""
        logger.info(f"Starting research on: {self.state.topic}")
        self.state.context.research_topic = self.state.topic
        self.state.context.research_objective = self.state.objective
        
        # 记录记忆：开始调研
        if self.state.memory:
            await self.state.memory.update_agent_state(
                state_data={"topic": self.state.topic, "phase": "initialization"},
                description=f"开始调研主题: {self.state.topic}"
            )
        
        queries = await self.query_gen.generate_queries(
            research_topic=self.state.topic,
            research_context={},
            knowledge_gaps=[],
            iteration_number=1,
            max_queries=3
        )
        self.state.queries = queries
        logger.info(f"Generated {len(queries)} initial queries")
        return None  # 防止 Flow 将起始结果作为最终结果返回

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
            
            # 第三阶段：将发现存入知识库
            if self.state.knowledge_base:
                await self.state.knowledge_base.add_text(
                    text=summary,
                    metadata={
                        "topic": self.state.topic,
                        "query": query.query,
                        "iteration": 1,
                        "type": "research_summary"
                    }
                )
            
        iteration.analysis_summary = "\n\n".join(self.state.summaries)
        self.state.context.add_iteration(iteration)
        
        # 记录记忆：完成搜索
        if self.state.memory:
            await self.state.memory.add(
                content=f"完成第一轮搜索总结，发现 {len(self.state.summaries)} 条关键线索。",
                importance=2,
                source="summarizer"
            )
            
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
        
        # 第三阶段：将最终报告存入知识库
        if self.state.knowledge_base:
            await self.state.knowledge_base.add_text(
                text=report,
                metadata={
                    "topic": self.state.topic,
                    "type": "final_report",
                    "objective": self.state.objective
                }
            )
            
        # 记录记忆：调研完成
        if self.state.memory:
            await self.state.memory.update_agent_state(
                state_data={"topic": self.state.topic, "phase": "completed"},
                description=f"完成调研并生成报告: {self.state.topic}"
            )
            
        logger.info("Final report generated and stored in KB")
        return report
