"""
Advanced Research Flow (v3 - with FlowEventEmitter)

基于 agenticx.flow 实现的带条件路由的深度研究工作流。
集成了 AdaptivePlanner，支持基于执行快照的智能重规划。
v3 新增：细粒度 FlowEventEmitter 事件钩子，支持实时 SSE 进度推送。
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from agenticx.flow.base import Flow
from agenticx.flow.decorators import start, listen, router, or_
from agenticx.llms.base import BaseLLMProvider
from agenticx.planner.adaptive_planner import AdaptivePlanner, ExecutionPlan, PlanPatch
from agenticx.flow.execution_plan import ExecutionStage, Subtask
from agenticx.knowledge.base import BaseKnowledge
from agenticx.brain.manager import BrainManager
from agenticx.memory.core_memory import CoreMemory
from agenticx.knowledge.graphers.builder import KnowledgeGraphBuilder as GraphBuilder

from agents import (
    QueryGeneratorAgent,
    ResearchSummarizerAgent,
    SearchAnalyzerAgent,
    ReportWriterAgent,
)
from models import ResearchContext, SearchQuery, ResearchIteration, KnowledgeGap
from tools import BaseSearchTool
from .basic_flow import ResearchState

logger = logging.getLogger(__name__)


class _NoopGraphBuilder:
    async def build_from_text(self, *args, **kwargs):
        class GraphData:
            entities = []

        return GraphData()


class AdvancedResearchFlow(Flow[ResearchState]):
    """深度研究工作流 (带 AdaptivePlanner, 多脑协同, 长程记忆, GraphRAG 和细粒度事件钩子)

    流程：
    initialize_research -> generate_queries -> execute_search_and_summarize
                        -> adaptive_replanning -> [router]
                                                    |          |
                                                 continue   write_report -> finalize_report
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        search_tools: List[BaseSearchTool],
        knowledge_base: Optional[BaseKnowledge] = None,
        memory: Optional[CoreMemory] = None,
        mounted_brains: Optional[List[str]] = None,
        enable_graph_export: bool = True,
        max_iterations: int = 5,
        min_completeness: float = 0.8,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.llm = llm_provider
        self.search_tools = search_tools
        self.max_iterations = max_iterations
        self.min_completeness = min_completeness
        self.enable_graph_export = enable_graph_export

        # 第三阶段：多脑管理
        self.brain_manager = BrainManager.instance()
        self.mounted_brains = mounted_brains or []

        # 初始化 Agents
        self.query_gen = QueryGeneratorAgent(llm_provider=self.llm)
        self.summarizer = ResearchSummarizerAgent(
            llm_provider=self.llm,
            search_tools=self.search_tools
        )
        self.analyzer = SearchAnalyzerAgent(llm_provider=self.llm)
        self.report_writer = ReportWriterAgent(llm_provider=self.llm)

        # 初始化 Planner
        self.planner = AdaptivePlanner(llm=self.llm)
        self.execution_plan: Optional[ExecutionPlan] = None

        # 注入知识库和记忆
        if knowledge_base:
            self.state.knowledge_base = knowledge_base
        if memory:
            self.state.memory = memory

        # GraphRAG 导出器（AgenticX versions differ on constructor shape）
        try:
            self.graph_builder = GraphBuilder(llm=self.llm)
        except TypeError:
            try:
                self.graph_builder = GraphBuilder(config={}, llm_config={})
            except Exception:
                self.graph_builder = _NoopGraphBuilder()

    # ------------------------------------------------------------------
    # 内部辅助：安全发射事件
    # ------------------------------------------------------------------
    async def _emit(self, method_name: str, *args, **kwargs):
        emitter = self.state.emitter
        if emitter and hasattr(emitter, method_name):
            try:
                await getattr(emitter, method_name)(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Event emit failed [{method_name}]: {e}")

    async def _generate_initial_plan(self, goal: str, context: str = "") -> ExecutionPlan:
        if hasattr(self.planner, "generate_initial_plan"):
            return await self.planner.generate_initial_plan(goal=goal, context=context)

        plan = ExecutionPlan(
            goal=goal,
            planning_logic="DeepResearch fallback plan generated for current AgenticX AdaptivePlanner API.",
            max_epochs=self.max_iterations,
        )
        stage_specs = [
            (
                "背景与现状梳理",
                "厘清主题背景、关键概念、最新动态和核心利益相关方。",
                ["主题背景", "最新动态", "关键参与方"],
            ),
            (
                "影响面分析",
                "分析经济、产业、资本市场、技术生态和潜在风险影响。",
                ["经济影响", "产业影响", "资本市场影响", "技术生态影响"],
            ),
            (
                "综合判断与报告",
                "交叉验证主要发现，形成结论、风险提示和后续观察点。",
                ["关键结论", "风险与不确定性", "后续观察点"],
            ),
        ]
        for stage_name, description, queries in stage_specs:
            stage = ExecutionStage(name=stage_name, description=description)
            for query in queries:
                stage.add_subtask(Subtask(name=query, query=f"{goal} {query}"))
            plan.add_stage(stage)
        return plan

    async def _propose_plan_patch(self, observation: str) -> Optional[PlanPatch]:
        if hasattr(self.planner, "propose_plan_patch"):
            return await self.planner.propose_plan_patch(
                plan=self.execution_plan,
                observation=observation,
            )
        # Current AgenticX AdaptivePlanner.replan expects a different LLM protocol
        # (`generate`) than KimiProvider exposes, so skip optional replanning here.
        return None

    def _patch_has_changes(self, patch: Optional[PlanPatch]) -> bool:
        if not patch:
            return False
        if hasattr(patch, "is_empty"):
            return not patch.is_empty
        return any(
            getattr(patch, attr, None)
            for attr in ("operations", "added_stages", "added_subtasks", "deleted_subtasks")
        )

    def _patch_change_count(self, patch: PlanPatch) -> int:
        if hasattr(patch, "operations"):
            return len(patch.operations or [])
        return len(getattr(patch, "added_subtasks", []) or []) + len(getattr(patch, "added_stages", []) or [])

    def _apply_plan_patch(self, patch: PlanPatch) -> None:
        if hasattr(self.execution_plan, "apply_patch"):
            self.execution_plan.apply_patch(patch)
        elif hasattr(self.planner, "apply_patch"):
            self.execution_plan = self.planner.apply_patch(self.execution_plan, patch)

    # ------------------------------------------------------------------
    # Flow 步骤
    # ------------------------------------------------------------------

    @start()
    async def initialize_research(self):
        """初始化研究上下文并生成初始执行计划"""
        logger.info(f"Initializing deep research with Adaptive Planning: {self.state.topic}")
        self.state.context.research_topic = self.state.topic
        self.state.context.research_objective = self.state.objective
        self.state.context.current_iteration = 0

        # 事件：任务开始
        await self._emit("emit_task_started", self.state.topic, "advanced")
        await self._emit("emit_phase_started", "initialize",
                         "正在初始化多脑协同与自适应规划引擎...", 2)

        # 记录记忆
        if self.state.memory:
            await self.state.memory.update_agent_state(
                state_data={"topic": self.state.topic, "mode": "advanced"},
                description=f"开始高级深度调研: {self.state.topic}"
            )

        # 第三阶段：从挂载的脑中检索背景知识
        background_context = ""
        if self.mounted_brains:
            logger.info(f"Retrieving background context from {len(self.mounted_brains)} mounted brains...")
            await self._emit("emit_phase_started", "brain_retrieval",
                             f"从 {len(self.mounted_brains)} 个知识脑中检索背景知识...", len(self.mounted_brains))
            for brain_id in self.mounted_brains:
                try:
                    runtime = self.brain_manager.get_runtime(brain_id)
                    search_response = await runtime.search(self.state.topic, limit=3)
                    if search_response and hasattr(search_response, 'hits') and search_response.hits:
                        hits_content = [hit.content for hit in search_response.hits]
                        background_context += f"\n[Brain: {brain_id}] " + "\n".join(hits_content)
                except Exception as e:
                    logger.warning(f"Failed to search brain {brain_id}: {e}")

        # 生成初始计划
        logger.info("Generating initial execution plan...")
        self.execution_plan = await self._generate_initial_plan(
            goal=f"对主题 '{self.state.topic}' 进行深度调研。目标: {self.state.objective or '全面了解'}",
            context=background_context
        )
        stage_count = len(self.execution_plan.stages)
        logger.info(f"Initial plan created with {stage_count} stages")

        # 事件：计划生成完成
        await self._emit("emit_phase_completed", "initialize",
                         f"初始执行计划已生成，包含 {stage_count} 个研究阶段")

        if self.state.memory:
            await self.state.memory.add(
                content=f"已生成初始执行计划，包含 {stage_count} 个阶段。",
                importance=3
            )
        # 不返回值，防止 Flow 提前结束

    @listen(or_(initialize_research, "continue_search"))
    async def generate_queries(self):
        """基于当前计划阶段生成查询"""
        self.state.context.current_iteration += 1
        it_num = self.state.context.current_iteration

        # 事件：阶段开始
        await self._emit("emit_phase_started", "generate_queries",
                         f"第 {it_num} 轮：正在基于执行计划生成搜索查询...", 5)

        # 获取当前执行计划中的活动子任务
        current_stage = self.execution_plan.current_stage
        subtasks = current_stage.get_pending_subtasks() if current_stage else []
        subtask_context = ", ".join([s.query for s in subtasks]) if subtasks else "常规搜索"

        logger.info(f"--- Iteration {it_num} (Stage: {current_stage.name if current_stage else 'N/A'}) ---")

        queries = await self.query_gen.generate_queries(
            research_topic=self.state.topic,
            research_context={"subtask_context": subtask_context},
            knowledge_gaps=[],
            iteration_number=it_num,
            max_queries=3
        )
        self.state.queries = queries

        # 事件：逐条发射生成的查询
        for i, q in enumerate(queries, 1):
            await self._emit("emit_query_generated", q.query, i, len(queries))

        # 将子任务状态标记为执行中
        for s in subtasks:
            s.mark_executing()

        # 事件：阶段完成
        await self._emit("emit_phase_completed", "generate_queries",
                         f"已生成 {len(queries)} 条搜索查询")

    @listen(generate_queries)
    async def execute_search_and_summarize(self):
        """执行搜索并汇总本轮发现"""
        queries = self.state.queries
        total = len(queries)
        it_num = self.state.context.current_iteration

        # 事件：阶段开始
        await self._emit("emit_phase_started", "search_and_summarize",
                         f"第 {it_num} 轮：执行 {total} 条查询的深度搜索...", total)

        iteration = ResearchIteration(
            iteration_id=it_num,
            queries=queries
        )

        async def summarize_one(idx: int, query: SearchQuery) -> str:
            logger.info(f"Searching: {query.query}")

            # 事件：单次搜索开始
            await self._emit("emit_search_started", query.query)

            summary = await self.summarizer.search_and_summarize(
                query=query.query,
                research_topic=self.state.topic
            )

            # 事件：搜索完成 + 摘要生成
            await self._emit("emit_search_completed", query.query, 1)
            await self._emit("emit_summary_generated", query.query, len(summary))

            # 第三阶段：存入知识库
            if self.state.knowledge_base:
                await self.state.knowledge_base.add_text(
                    text=summary,
                    metadata={
                        "topic": self.state.topic,
                        "query": query.query,
                        "iteration": it_num,
                        "type": "research_summary"
                    }
                )
                await self._emit("emit_knowledge_indexed", idx)
            return summary

        round_summaries = []
        if queries:
            semaphore = asyncio.Semaphore(2)

            async def summarize_with_limit(idx: int, query: SearchQuery) -> str:
                async with semaphore:
                    return await summarize_one(idx, query)

            round_summaries = await asyncio.gather(
                *(summarize_with_limit(idx, query) for idx, query in enumerate(queries, 1))
            )

        iteration.analysis_summary = "\n\n".join(round_summaries)
        self.state.context.add_iteration(iteration)
        self.state.summaries.extend(round_summaries)

        # 更新当前阶段子任务为完成
        if self.execution_plan.current_stage:
            from agenticx.flow.execution_plan import SubtaskStatus
            for s in self.execution_plan.current_stage.subtasks:
                if s.status == SubtaskStatus.EXECUTING:
                    s.mark_completed(result=iteration.analysis_summary[:200] + "...")

            if all(s.status == SubtaskStatus.COMPLETED for s in self.execution_plan.current_stage.subtasks):
                self.execution_plan.current_stage.complete(summary=iteration.analysis_summary[:200] + "...")
                self.execution_plan.current_stage_index += 1

        # 事件：迭代完成
        await self._emit("emit_phase_completed", "search_and_summarize",
                         f"第 {it_num} 轮搜索完成，共获得 {len(round_summaries)} 条摘要")

        return iteration

    @listen(execute_search_and_summarize)
    async def adaptive_replanning(self):
        """动态重规划"""
        logger.info("Performing adaptive re-planning...")

        # 事件：规划阶段开始
        await self._emit("emit_phase_started", "adaptive_planning",
                         "正在分析调研进度，执行自适应重规划...", 1)

        # 反思当前进度
        reflection = await self.summarizer.reflect(
            research_topic=self.state.topic,
            current_summary="\n\n".join(self.state.summaries),
            iteration_number=self.state.context.current_iteration
        )

        completeness = reflection.get("completeness_score", 0.5)

        # 记录记忆
        if self.state.memory:
            await self.state.memory.add(
                content=f"迭代 {self.state.context.current_iteration} 反思: {reflection.get('reflection_summary', '')}",
                importance=4
            )

        # 调用 AdaptivePlanner 提出计划修补方案
        patch: Optional[PlanPatch] = await self._propose_plan_patch(
            observation=f"当前迭代发现: {reflection.get('reflection_summary', '')}\n知识空白: {reflection.get('identified_gaps', [])}"
        )

        if self._patch_has_changes(patch):
            logger.info("Applying plan patch...")
            self._apply_plan_patch(patch)

            # 事件：计划修补
            added_count = self._patch_change_count(patch)
            await self._emit("emit_plan_patched",
                             f"发现新线索，动态扩展 {added_count} 个研究子任务",
                             added_count)

            if self.state.memory:
                await self.state.memory.add(content="执行计划已根据新发现动态调整。", importance=3)
        else:
            from agenticx.flow.execution_plan import StageStatus
            if self.execution_plan.current_stage and self.execution_plan.current_stage.status == StageStatus.DONE:
                self.execution_plan.current_stage_index += 1

        # 事件：规划完成
        await self._emit("emit_phase_completed", "adaptive_planning",
                         f"重规划完成，当前完成度 {completeness:.0%}")

        return {
            "reflection": reflection,
            "completeness": completeness,
            "is_plan_done": self.execution_plan.is_completed
        }

    @router(adaptive_replanning)
    def route_research(self, result: Dict[str, Any]):
        """根据计划状态和完成度路由"""
        completeness = result.get("completeness", 0.0)
        is_plan_done = result.get("is_plan_done", False)
        it_num = self.state.context.current_iteration

        if is_plan_done or completeness >= self.min_completeness or it_num >= self.max_iterations:
            return "write_report"
        else:
            return "continue_search"

    @listen("write_report")
    async def finalize_report(self):
        """生成最终报告并导出知识图谱"""
        logger.info("Generating final report and exporting to GraphRAG...")

        # 事件：报告开始
        await self._emit("emit_report_started")
        await self._emit("emit_phase_started", "write_report",
                         "正在综合所有调研结果，撰写深度报告...", 1)

        report_obj = await self.report_writer.generate_report(
            research_context=self.state.context
        )
        report = report_obj.to_markdown()
        self.state.final_report = report

        # 第三阶段：将最终报告存入知识库
        if self.state.knowledge_base:
            await self.state.knowledge_base.add_text(
                text=report,
                metadata={"topic": self.state.topic, "type": "final_report"}
            )

        # 第三阶段：自动导出至 GraphRAG
        if self.enable_graph_export and self.state.knowledge_base:
            try:
                logger.info("Building knowledge graph from research findings...")
                graph_data = await self.graph_builder.build_from_text(
                    text="\n\n".join(self.state.summaries) + "\n\n" + report,
                    topic=self.state.topic
                )
                if hasattr(self.state.knowledge_base, 'add_graph'):
                    await self.state.knowledge_base.add_graph(graph_data)
                    entity_count = len(graph_data.entities)
                    logger.info(f"Successfully exported {entity_count} entities to GraphRAG.")
                    await self._emit("emit_knowledge_indexed", entity_count)
            except Exception as e:
                logger.error(f"Failed to export to GraphRAG: {e}")

        if self.state.memory:
            await self.state.memory.add(
                content=f"调研报告已生成并同步至知识图谱，主题: {self.state.topic}",
                importance=5
            )

        # 事件：报告完成 + 任务完成
        await self._emit("emit_report_completed", len(report))
        await self._emit("emit_phase_completed", "write_report", "深度报告撰写完成")
        await self._emit("emit_task_completed", self.state.context.research_topic, report[:200])

        return report
