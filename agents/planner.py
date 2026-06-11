"""
Planner Agent

基于 AgenticX 框架的研究规划智能体。
负责制定研究策略、识别知识空白、决定迭代方向。
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agenticx.core.agent import Agent, AgentContext, AgentResult
from agenticx.llms.base import BaseLLMProvider

from models import (
    ResearchContext,
    KnowledgeGap,
    ResearchIteration,
    ResearchPhase,
    QueryType,
)

logger = logging.getLogger(__name__)


class PlannerAgent(Agent):
    """研究规划智能体
    
    基于 agenticx.core.Agent 实现，负责：
    1. 制定研究策略和计划
    2. 识别知识空白和研究方向
    3. 决定是否继续迭代
    4. 调整搜索策略
    """

    def __init__(
        self,
        name: str = "研究规划专家",
        role: str = "研究规划策略师",
        goal: str = "制定高效研究策略，识别知识空白，引导多轮反思式研究过程",
        organization_id: str = "deepsearch",
        llm_provider: Optional[Any] = None,
        **kwargs
    ):
        super().__init__(
            name=name,
            role=role,
            goal=goal,
            organization_id=organization_id,
            backstory=(
                "你是一位经验丰富的研究规划专家，擅长分析复杂研究问题、"
                "识别知识空白、制定系统化研究策略。你能从宏观视角把握研究方向，"
                "确保研究过程的完整性和深度。"
            ),
            **kwargs
        )

        # 使用 object.__setattr__ 绕过 Pydantic 验证
        object.__setattr__(self, "llm", llm_provider)

    # ========================================================================
    # 公共接口
    # ========================================================================

    async def create_initial_research_plan(
        self,
        research_topic: str,
        research_objective: str = "",
        max_iterations: int = 5,
    ) -> Dict[str, Any]:
        """创建初始研究计划
        
        Args:
            research_topic: 研究主题
            research_objective: 研究目标
            max_iterations: 最大迭代次数
            
        Returns:
            研究计划字典
        """
        language = self._detect_language(research_topic)

        if language == "zh":
            prompt = f"""你是一位研究规划专家。请为以下研究主题制定详细的研究计划。

研究主题: {research_topic}
研究目标: {research_objective or '深入了解该主题的各个方面'}
最大迭代次数: {max_iterations}

请制定研究计划，包括：
1. 研究范围和边界
2. 关键研究问题（3-5个）
3. 研究阶段划分
4. 每个阶段的搜索策略
5. 预期成果

请以JSON格式返回：
{{
    "scope": "研究范围描述",
    "key_questions": ["问题1", "问题2", ...],
    "phases": [
        {{"phase": "阶段名", "strategy": "策略描述", "focus": "重点方向"}}
    ],
    "expected_outcomes": ["预期成果1", "预期成果2"],
    "search_strategy": {{
        "engines": ["bochaai", "google"],
        "language": "zh-CN",
        "depth": "comprehensive"
    }}
}}
"""
        else:
            prompt = f"""You are a research planning expert. Create a detailed research plan.

Research Topic: {research_topic}
Objective: {research_objective or 'Comprehensive understanding of the topic'}
Max Iterations: {max_iterations}

Create a plan including:
1. Research scope and boundaries
2. Key research questions (3-5)
3. Phase breakdown
4. Search strategy per phase
5. Expected outcomes

Return in JSON:
{{
    "scope": "scope description",
    "key_questions": ["q1", "q2", ...],
    "phases": [
        {{"phase": "name", "strategy": "description", "focus": "focus area"}}
    ],
    "expected_outcomes": ["outcome1", "outcome2"],
    "search_strategy": {{
        "engines": ["bochaai", "google"],
        "language": "en-US",
        "depth": "comprehensive"
    }}
}}
"""

        if self.llm:
            try:
                response = await self.llm.ainvoke(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                plan = self._extract_json(text)
                if plan:
                    return plan
            except Exception as e:
                logger.warning(f"[Planner] LLM 调用失败: {e}")

        # 回退默认计划
        return {
            "scope": f"全面研究 {research_topic}",
            "key_questions": [
                f"{research_topic} 的核心概念是什么？",
                f"{research_topic} 的最新进展有哪些？",
                f"{research_topic} 的主要挑战是什么？",
            ],
            "phases": [
                {"phase": "广度探索", "strategy": "broad_exploration", "focus": "基础概念"},
                {"phase": "深度挖掘", "strategy": "focused_deep_dive", "focus": "技术细节"},
                {"phase": "验证整合", "strategy": "verification", "focus": "交叉验证"},
            ],
            "expected_outcomes": ["综合研究报告", "知识图谱"],
            "search_strategy": {
                "engines": ["bochaai"],
                "language": "zh-CN" if language == "zh" else "en-US",
                "depth": "comprehensive",
            },
        }

    async def identify_knowledge_gaps(
        self,
        research_context: ResearchContext,
        current_findings: str = "",
    ) -> List[KnowledgeGap]:
        """识别知识空白
        
        Args:
            research_context: 研究上下文
            current_findings: 当前发现摘要
            
        Returns:
            KnowledgeGap 列表
        """
        language = self._detect_language(research_context.research_topic)

        # 汇总已有搜索结果
        results_summary = self._summarize_search_results(research_context)

        if language == "zh":
            prompt = f"""你是一位研究分析专家。请根据以下信息识别当前研究中的知识空白。

研究主题: {research_context.research_topic}
研究目标: {research_context.research_objective}
当前迭代: 第{research_context.current_iteration}轮
已有发现摘要: {current_findings or results_summary}

请识别3-5个知识空白，以JSON格式返回：
{{
    "gaps": [
        {{
            "topic": "空白主题",
            "description": "详细描述",
            "priority": 8,
            "suggested_queries": ["建议查询1", "建议查询2"]
        }}
    ]
}}
"""
        else:
            prompt = f"""You are a research analysis expert. Identify knowledge gaps.

Topic: {research_context.research_topic}
Objective: {research_context.research_objective}
Iteration: {research_context.current_iteration}
Findings: {current_findings or results_summary}

Identify 3-5 gaps in JSON:
{{
    "gaps": [
        {{
            "topic": "gap topic",
            "description": "detailed description",
            "priority": 8,
            "suggested_queries": ["query1", "query2"]
        }}
    ]
}}
"""

        if self.llm:
            try:
                response = await self.llm.ainvoke(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                parsed = self._extract_json(text)
                gaps_data = parsed.get("gaps", [])
                return [
                    KnowledgeGap(
                        topic=g.get("topic", ""),
                        description=g.get("description", ""),
                        priority=g.get("priority", 5),
                        suggested_queries=g.get("suggested_queries", []),
                        identified_by=self.name,
                    )
                    for g in gaps_data
                    if g.get("topic")
                ]
            except Exception as e:
                logger.warning(f"[Planner] 知识空白识别失败: {e}")

        return []

    async def should_continue_research(
        self,
        research_context: ResearchContext,
        current_findings: str = "",
    ) -> Dict[str, Any]:
        """判断是否应继续研究
        
        Returns:
            {"should_continue": bool, "reason": str, "next_focus": str}
        """
        # 基本终止条件
        if research_context.current_iteration >= research_context.max_iterations:
            return {
                "should_continue": False,
                "reason": "已达到最大迭代次数",
                "next_focus": "",
            }

        language = self._detect_language(research_context.research_topic)
        results_summary = self._summarize_search_results(research_context)

        if language == "zh":
            prompt = f"""你是一位研究规划专家。请判断是否应该继续研究。

研究主题: {research_context.research_topic}
当前迭代: 第{research_context.current_iteration}/{research_context.max_iterations}轮
已有发现: {current_findings or results_summary}

请判断：
1. 当前信息是否足够回答研究问题？
2. 是否还有重要的知识空白？
3. 继续研究的边际收益如何？

以JSON返回：
{{"should_continue": true/false, "reason": "原因", "next_focus": "下一步重点"}}
"""
        else:
            prompt = f"""You are a research planning expert. Decide whether to continue.

Topic: {research_context.research_topic}
Iteration: {research_context.current_iteration}/{research_context.max_iterations}
Findings: {current_findings or results_summary}

Evaluate:
1. Is current info sufficient?
2. Are there important gaps?
3. What's the marginal benefit?

Return JSON: {{"should_continue": true/false, "reason": "reason", "next_focus": "next focus"}}
"""

        if self.llm:
            try:
                response = await self.llm.ainvoke(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                result = self._extract_json(text)
                if "should_continue" in result:
                    return result
            except Exception as e:
                logger.warning(f"[Planner] 判断失败: {e}")

        # 默认：如果还有迭代空间则继续
        return {
            "should_continue": research_context.current_iteration < research_context.max_iterations,
            "reason": "默认策略：继续至最大迭代",
            "next_focus": "深入探索",
        }

    async def adjust_search_strategy(
        self,
        research_context: ResearchContext,
        performance_metrics: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """调整搜索策略
        
        Returns:
            调整后的策略字典
        """
        language = self._detect_language(research_context.research_topic)
        metrics_str = json.dumps(performance_metrics or {}, ensure_ascii=False)

        if language == "zh":
            prompt = f"""你是搜索策略优化专家。请根据当前研究表现调整搜索策略。

研究主题: {research_context.research_topic}
当前迭代: 第{research_context.current_iteration}轮
性能指标: {metrics_str}

请建议策略调整，以JSON返回：
{{
    "engines": ["bochaai", "google"],
    "query_style": "focused/broad/comparative",
    "language": "zh-CN",
    "freshness": "week/month/year/null",
    "max_results_per_query": 10,
    "reasoning": "调整理由"
}}
"""
        else:
            prompt = f"""You are a search strategy expert. Adjust strategy based on performance.

Topic: {research_context.research_topic}
Iteration: {research_context.current_iteration}
Metrics: {metrics_str}

Suggest adjustments in JSON:
{{
    "engines": ["bochaai", "google"],
    "query_style": "focused/broad/comparative",
    "language": "en-US",
    "freshness": "week/month/year/null",
    "max_results_per_query": 10,
    "reasoning": "reasoning"
}}
"""

        if self.llm:
            try:
                response = await self.llm.ainvoke(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                result = self._extract_json(text)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"[Planner] 策略调整失败: {e}")

        return {
            "engines": ["bochaai"],
            "query_style": "focused",
            "language": "zh-CN" if language == "zh" else "en-US",
            "freshness": None,
            "max_results_per_query": 10,
            "reasoning": "默认策略",
        }

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _summarize_search_results(self, context: ResearchContext) -> str:
        """汇总搜索结果为文本摘要"""
        all_results = context.get_all_search_results()
        if not all_results:
            return "暂无搜索结果"

        summaries = []
        for i, result in enumerate(all_results[:20]):
            if isinstance(result, dict):
                title = result.get("title", "")
                snippet = result.get("snippet", "")
            else:
                title = getattr(result, "title", "")
                snippet = getattr(result, "snippet", "")
            summaries.append(f"{i+1}. {title}: {snippet[:100]}")

        return "\n".join(summaries)

    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "zh" if chinese_chars > len(text) * 0.3 else "en"

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从 LLM 响应中提取 JSON"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {}
