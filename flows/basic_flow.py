"""
Basic Research Flow (v3 - with FlowEventEmitter)

基于 agenticx.flow 实现的线性研究工作流。
v3 新增：细粒度 FlowEventEmitter 事件钩子，支持实时 SSE 进度推送。
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

    # 第三阶段：统一知识库和记忆接口
    knowledge_base: Optional[BaseKnowledge] = None
    memory: Optional[CoreMemory] = None

    # 第四阶段：事件发射器（由 API 层注入）
    emitter: Optional[Any] = None  # FlowEventEmitter，避免循环导入用 Any


class BasicResearchFlow(Flow[ResearchState]):
    """基础研究工作流 (线性)

    流程：
    generate_initial_queries -> search_and_summarize -> write_report

    v3 新增：每个步骤内部通过 FlowEventEmitter 发射细粒度事件。
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

    # ------------------------------------------------------------------
    # 内部辅助：安全发射事件（emitter 可能未注入）
    # ------------------------------------------------------------------
    async def _emit(self, method_name: str, *args, **kwargs):
        emitter = self.state.emitter
        if emitter and hasattr(emitter, method_name):
            try:
                await getattr(emitter, method_name)(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Event emit failed [{method_name}]: {e}")

    # ------------------------------------------------------------------
    # Flow 步骤
    # ------------------------------------------------------------------

    @start()
    async def generate_initial_queries(self):
        """第一步：生成初始查询"""
        logger.info(f"Starting research on: {self.state.topic}")
        self.state.context.research_topic = self.state.topic
        self.state.context.research_objective = self.state.objective

        # 事件：任务开始
        await self._emit("emit_task_started", self.state.topic, "basic")
        # 事件：阶段开始
        await self._emit("emit_phase_started", "generate_queries", "正在分析主题，生成搜索查询...", 3)

        # 记录记忆
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

        # 事件：逐条发射生成的查询
        for i, q in enumerate(queries, 1):
            await self._emit("emit_query_generated", q.query, i, len(queries))

        # 事件：阶段完成
        await self._emit("emit_phase_completed", "generate_queries", f"已生成 {len(queries)} 条搜索查询")

        logger.info(f"Generated {len(queries)} initial queries")
        return None  # 防止 Flow 将起始结果作为最终结果返回

    @listen(generate_initial_queries)
    async def search_and_summarize(self):
        """第二步：执行搜索并总结"""
        queries = self.state.queries
        total = len(queries)

        # 事件：阶段开始
        await self._emit("emit_phase_started", "search_and_summarize",
                         f"开始执行 {total} 条查询的搜索与摘要...", total)

        iteration = ResearchIteration(iteration_id=1, queries=queries)

        for idx, query in enumerate(queries, 1):
            logger.info(f"Executing search for: {query.query}")

            # 事件：单次搜索开始
            await self._emit("emit_search_started", query.query)

            summary = await self.summarizer.search_and_summarize(
                query=query.query,
                research_topic=self.state.topic
            )
            self.state.summaries.append(summary)

            # 事件：单次搜索完成
            await self._emit("emit_search_completed", query.query, 1)
            # 事件：摘要生成
            await self._emit("emit_summary_generated", query.query, len(summary))

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
                await self._emit("emit_knowledge_indexed", idx)

        iteration.analysis_summary = "\n\n".join(self.state.summaries)
        self.state.context.add_iteration(iteration)

        # 记录记忆
        if self.state.memory:
            await self.state.memory.add(
                content=f"完成第一轮搜索总结，发现 {len(self.state.summaries)} 条关键线索。",
                importance=2,
                source="summarizer"
            )

        # 事件：阶段完成
        await self._emit("emit_phase_completed", "search_and_summarize",
                         f"搜索与摘要完成，共处理 {total} 条查询")
        logger.info("Search and summarization completed")

    @listen(search_and_summarize)
    async def write_report(self):
        """第三步：撰写最终报告"""
        logger.info("Generating final report...")

        # 事件：报告开始
        await self._emit("emit_report_started")
        await self._emit("emit_phase_started", "write_report", "正在综合所有调研结果，撰写深度报告...", 1)

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

        # 记录记忆
        if self.state.memory:
            await self.state.memory.update_agent_state(
                state_data={"topic": self.state.topic, "phase": "completed"},
                description=f"完成调研并生成报告: {self.state.topic}"
            )

        # 事件：报告完成 + 任务完成
        await self._emit("emit_report_completed", len(report))
        await self._emit("emit_phase_completed", "write_report", "报告撰写完成")
        await self._emit("emit_task_completed", self.state.context.research_topic, report[:200])

        logger.info("Final report generated and stored in KB")
        return report
