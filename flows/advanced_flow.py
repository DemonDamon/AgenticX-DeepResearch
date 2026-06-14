"""
Advanced Research Flow (v2 - agenticx.flow Based)

基于 agenticx.flow 实现的带条件路由的深度研究工作流。
集成了 AdaptivePlanner，支持基于执行快照的智能重规划。
"""

import logging
from typing import Any, Dict, List, Optional, Union

from pydantic import Field

from agenticx.flow.base import Flow
from agenticx.flow.decorators import start, listen, router, or_
from agenticx.llms.base import BaseLLMProvider
from agenticx.planner.adaptive_planner import AdaptivePlanner, ExecutionPlan, PlanPatch

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


class AdvancedResearchFlow(Flow[ResearchState]):
    """深度研究工作流 (带 AdaptivePlanner)
    
    流程：
    Start -> Initial Plan -> Generate Queries -> Search & Summarize -> Analyze & Re-plan -> [Router]
                                                                        |               |
                                                                        V               V
                                                                   Apply Patch      Write Report
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        search_tools: List[BaseSearchTool],
        max_iterations: int = 5,
        min_completeness: float = 0.8,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.llm = llm_provider
        self.search_tools = search_tools
        self.max_iterations = max_iterations
        self.min_completeness = min_completeness
        
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

    @start()
    async def initialize_research(self):
        """初始化研究上下文并生成初始执行计划"""
        logger.info(f"Initializing deep research with Adaptive Planning: {self.state.topic}")
        self.state.context.research_topic = self.state.topic
        self.state.context.research_objective = self.state.objective
        self.state.context.current_iteration = 0
        
        # 生成初始计划
        logger.info("Generating initial execution plan...")
        self.execution_plan = await self.planner.generate_initial_plan(
            goal=f"对主题 '{self.state.topic}' 进行深度调研。目标: {self.state.objective or '全面了解'}"
        )
        logger.info(f"Initial plan created with {len(self.execution_plan.stages)} stages")

    @listen(or_(initialize_research, "continue_search"))
    async def generate_queries(self):
        """基于当前计划阶段生成查询"""
        self.state.context.current_iteration += 1
        it_num = self.state.context.current_iteration
        
        # 获取当前执行计划中的活动子任务
        current_stage = self.execution_plan.current_stage
        subtasks = current_stage.get_pending_subtasks() if current_stage else []
        subtask_context = ", ".join([s.query for s in subtasks]) if subtasks else "常规搜索"
        
        logger.info(f"--- Iteration {it_num} (Stage: {current_stage.name if current_stage else 'N/A'}) ---")
        logger.info(f"Focusing on subtasks: {subtask_context}")

        queries = await self.query_gen.generate_queries(
            research_topic=self.state.topic,
            research_context={"subtask_context": subtask_context},
            knowledge_gaps=[],
            iteration_number=it_num,
            max_queries=5
        )
        self.state.queries = queries
        
        # 将子任务状态标记为执行中
        for s in subtasks:
            s.mark_executing()
            
        return queries

    @listen(generate_queries)
    async def execute_search_and_summarize(self):
        """执行搜索并汇总本轮发现"""
        iteration = ResearchIteration(
            iteration_id=self.state.context.current_iteration,
            queries=self.state.queries
        )
        
        round_summaries = []
        for query in self.state.queries:
            logger.info(f"Searching: {query.query}")
            summary = await self.summarizer.search_and_summarize(
                query=query.query,
                research_topic=self.state.topic
            )
            round_summaries.append(summary)
            
        iteration.analysis_summary = "\n\n".join(round_summaries)
        self.state.context.add_iteration(iteration)
        self.state.summaries.extend(round_summaries)
        
        # 更新当前阶段子任务为完成
        if self.execution_plan.current_stage:
            from agenticx.flow.execution_plan import SubtaskStatus
            for s in self.execution_plan.current_stage.subtasks:
                if s.status == SubtaskStatus.EXECUTING:
                    s.mark_completed(result=iteration.analysis_summary[:200] + "...")
            
            # 检查阶段是否完成
            if all(s.status == SubtaskStatus.COMPLETED for s in self.execution_plan.current_stage.subtasks):
                self.execution_plan.current_stage.complete(summary=iteration.analysis_summary[:200] + "...")
                self.execution_plan.current_stage_index += 1
                
        return iteration

    @listen(execute_search_and_summarize)
    async def adaptive_replanning(self):
        """动态重规划"""
        logger.info("Performing adaptive re-planning...")
        
        # 反思当前进度
        reflection = await self.summarizer.reflect(
            research_topic=self.state.topic,
            current_summary="\n\n".join(self.state.summaries),
            iteration_number=self.state.context.current_iteration
        )
        
        # 记录反思到状态
        completeness = reflection.get("completeness_score", 0.5)
        
        # 调用 AdaptivePlanner 提出计划修补方案
        logger.info("Proposing plan patch based on execution snapshot...")
        patch: PlanPatch = await self.planner.propose_plan_patch(
            plan=self.execution_plan,
            observation=f"当前迭代发现: {reflection.get('reflection_summary', '')}\n知识空白: {reflection.get('identified_gaps', [])}"
        )
        
        if patch and (patch.added_stages or patch.added_subtasks or patch.deleted_subtasks):
            logger.info(f"Applying plan patch: added {len(patch.added_stages)} stages, {len(patch.added_subtasks)} subtasks")
            self.execution_plan.apply_patch(patch)
        else:
            logger.info("No plan adjustments needed.")
            # 如果当前阶段已完成且没有 patch，尝试推进阶段
            from agenticx.flow.execution_plan import StageStatus
            if self.execution_plan.current_stage and self.execution_plan.current_stage.status == StageStatus.DONE:
                self.execution_plan.current_stage_index += 1
        
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
            logger.info("Research flow finishing (Plan done or threshold met).")
            return "write_report"
        else:
            return "continue_search"

    @listen("write_report")
    async def finalize_report(self):
        """生成最终报告"""
        logger.info("Generating final report with all gathered insights...")
        
        report_obj = await self.report_writer.generate_report(
            research_context=self.state.context
        )
        report = report_obj.to_markdown()
        self.state.final_report = report
        return report
