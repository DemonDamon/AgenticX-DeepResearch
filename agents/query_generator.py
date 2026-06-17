"""
Query Generator Agent (v2 - ReActAgent Based)

基于 AgenticX ReActAgent 异步版本的查询生成智能体。
利用 function calling 原生能力，通过 Tool 接口实现查询策略选择和生成。
支持流式事件输出和循环检测。
"""

import json
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from agenticx.agents.react_agent_async import ReActAgent, ReActResult
from agenticx.llms.base import BaseLLMProvider
from agenticx.tools.base import BaseTool

from models import SearchQuery, QueryType, KnowledgeGap, ResearchPhase, SearchEngine

logger = logging.getLogger(__name__)


# ============================================================================
# 查询策略与复杂度
# ============================================================================

class QueryStrategy(str, Enum):
    """查询策略"""
    BROAD_EXPLORATION = "broad_exploration"
    FOCUSED_DEEP_DIVE = "focused_deep_dive"
    GAP_FILLING = "gap_filling"
    VERIFICATION = "verification"
    COMPARATIVE = "comparative"
    TEMPORAL = "temporal"
    MULTI_PERSPECTIVE = "multi_perspective"


class QueryComplexity(str, Enum):
    """查询复杂度"""
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    EXPERT = "expert"


# ============================================================================
# Query Generation Tool (供 ReActAgent 调用)
# ============================================================================

class QueryGenerationTool(BaseTool):
    """查询生成工具
    
    封装查询生成的核心逻辑为 BaseTool，供 ReActAgent 通过 function calling 调用。
    支持多策略生成、模板回退和去重。
    """

    def __init__(self):
        super().__init__(
            name="generate_search_queries",
            description=(
                "根据研究主题、策略和知识空白生成搜索查询。"
                "输入参数: topic(研究主题), strategy(策略: broad_exploration/focused_deep_dive/"
                "gap_filling/verification/comparative/temporal/multi_perspective), "
                "max_queries(最大数量), knowledge_gaps(知识空白列表,可选), "
                "previous_queries(已有查询列表,可选), language(zh/en)"
            ),
        )
        self._generated_cache: Set[str] = set()
        self._query_templates = {
            QueryStrategy.BROAD_EXPLORATION: [
                "{topic} 概述",
                "{topic} 基本概念",
                "{topic} 发展历史",
                "{topic} 应用领域",
                "{topic} 最新进展",
            ],
            QueryStrategy.FOCUSED_DEEP_DIVE: [
                "{topic} 详细分析",
                "{topic} 技术原理",
                "{topic} 实现方法",
                "{topic} 案例研究",
                "{topic} 专家观点",
            ],
            QueryStrategy.GAP_FILLING: [
                "{topic} {gap_area}",
                "{gap_area} 在 {topic} 中的应用",
                "{topic} {gap_area} 解决方案",
            ],
            QueryStrategy.VERIFICATION: [
                "{topic} 验证方法",
                "{topic} 可靠性分析",
                "{topic} 对比研究",
            ],
            QueryStrategy.COMPARATIVE: [
                "{topic} vs {alternative}",
                "{topic} 对比分析",
                "{topic} 优劣势",
            ],
            QueryStrategy.TEMPORAL: [
                "{topic} 2025",
                "{topic} 最新动态",
                "{topic} 趋势分析",
                "{topic} 未来展望",
            ],
            QueryStrategy.MULTI_PERSPECTIVE: [
                "{topic} 技术视角",
                "{topic} 商业视角",
                "{topic} 社会影响",
                "{topic} 政策法规",
            ],
        }
        self._coverage_suffixes = [
            "市场规模",
            "关键趋势",
            "技术架构",
            "应用案例",
            "竞品对比",
            "风险挑战",
            "投资融资",
            "政策法规",
            "专家观点",
            "未来预测 2026",
            "最新数据",
            "开源生态",
        ]

    def _run(
        self,
        topic: str = "",
        strategy: str = "broad_exploration",
        max_queries: int = 5,
        knowledge_gaps: Optional[List[str]] = None,
        previous_queries: Optional[List[str]] = None,
        language: str = "zh",
        **kwargs,
    ) -> str:
        """同步执行查询生成（模板回退模式）"""
        try:
            strategy_enum = QueryStrategy(strategy)
        except ValueError:
            strategy_enum = QueryStrategy.BROAD_EXPLORATION

        templates = list(self._query_templates.get(strategy_enum, []))
        if max_queries > len(templates):
            templates.extend("{topic} " + suffix for suffix in self._coverage_suffixes)
        queries = []

        gap_area = knowledge_gaps[0] if knowledge_gaps else "核心问题"
        alternative = "替代方案"

        for template in templates:
            try:
                query = template.format(
                    topic=topic,
                    gap_area=gap_area,
                    alternative=alternative,
                )
                queries.append(query)
            except (KeyError, IndexError):
                queries.append(template.replace("{topic}", topic))

        # 去重
        prev_set = set(q.lower().strip() for q in (previous_queries or []))
        unique = []
        for q in queries:
            normalized = q.strip().lower()
            if normalized not in prev_set and normalized not in self._generated_cache:
                self._generated_cache.add(normalized)
                unique.append(q.strip())

        result = unique[:max_queries]
        return json.dumps({"queries": result}, ensure_ascii=False)


# ============================================================================
# Query Generator Agent (ReActAgent Wrapper)
# ============================================================================

class QueryGeneratorAgent:
    """查询生成智能体 (v2 - ReActAgent Based)
    
    基于 agenticx.agents.ReActAgent 异步版本实现：
    1. 原生 function calling 能力
    2. 流式事件输出 (astream)
    3. 循环检测与自动 nudge
    4. 多策略查询生成
    5. 知识空白导向查询
    6. 多语言查询支持
    
    Usage:
        agent = QueryGeneratorAgent(llm_provider=my_llm)
        queries = await agent.generate_queries(
            research_topic="人工智能最新进展",
            research_context={},
            knowledge_gaps=[],
            iteration_number=1,
        )
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        max_iterations: int = 5,
        **kwargs,
    ):
        self.id = "query_generator_agent"
        self.name = "查询生成专家"
        self.role = "Expert Search Query Formulator"
        self.tool_names: List[str] = []
        self.llm = llm_provider
        self._query_tool = QueryGenerationTool()
        self._max_iterations = max_iterations
        self._stats = {
            "total_generated": 0,
            "strategies_used": {},
        }

        # 构建 ReActAgent（如果有 LLM）
        self._react_agent: Optional[ReActAgent] = None
        if self.llm is not None:
            self._react_agent = ReActAgent(
                llm=self.llm,
                tools=[self._query_tool],
                system_prompt=self._build_system_prompt(),
                max_iterations=self._max_iterations,
            )

    def _build_system_prompt(self) -> str:
        return """你是一位专业的搜索查询策略师。你的任务是根据研究主题和上下文生成高质量的搜索查询。

你拥有以下能力：
1. 使用 generate_search_queries 工具生成搜索查询
2. 根据研究阶段选择最优策略
3. 针对知识空白生成补充查询
4. 确保查询多样性和去重

工作流程：
1. 分析用户的研究需求和当前阶段
2. 确定最佳查询策略
3. 调用工具生成查询
4. 如果需要，可以多次调用工具使用不同策略来丰富查询集
5. 最终返回所有生成的查询（JSON 格式）

最终输出格式（纯 JSON，不要 markdown 代码块）：
{"queries": ["query1", "query2", ...]}
"""

    # ========================================================================
    # 公共接口
    # ========================================================================

    async def generate_queries(
        self,
        research_topic: str,
        research_context: Dict[str, Any],
        knowledge_gaps: List[KnowledgeGap],
        iteration_number: int,
        max_queries: int = 10,
    ) -> List[SearchQuery]:
        """生成搜索查询（主入口）
        
        Args:
            research_topic: 研究主题
            research_context: 研究上下文
            knowledge_gaps: 知识空白列表
            iteration_number: 当前迭代轮次
            max_queries: 最大查询数
            
        Returns:
            SearchQuery 列表
        """
        language = self._detect_language(research_topic)
        strategy = self._determine_strategy(iteration_number, knowledge_gaps)

        # CLI 默认走直接模板生成，避免 ReAct 多轮调用导致启动慢或静默等待。
        if os.getenv("FAST_CLI", "1") == "1":
            queries = self._generate_with_tool_directly(
                research_topic, knowledge_gaps, strategy, max_queries, language
            )
        elif self._react_agent is not None:
            queries = await self._generate_with_react_agent(
                research_topic, research_context, knowledge_gaps,
                iteration_number, strategy, max_queries, language
            )
        else:
            # 回退到直接调用工具
            queries = self._generate_with_tool_directly(
                research_topic, knowledge_gaps, strategy, max_queries, language
            )

        # 转换为 SearchQuery 模型
        search_queries = []
        for q_text in queries[:max_queries]:
            sq = SearchQuery(
                query=q_text,
                query_type=self._infer_query_type(iteration_number, strategy),
                language="zh-CN" if language == "zh" else "en-US",
                max_results=10,
                search_engines=[SearchEngine.BOCHAAI],
            )
            search_queries.append(sq)

        # 更新统计
        self._stats["total_generated"] += len(search_queries)
        self._stats["strategies_used"][strategy.value] = (
            self._stats["strategies_used"].get(strategy.value, 0) + 1
        )

        return search_queries

    async def generate_queries_stream(
        self,
        research_topic: str,
        research_context: Dict[str, Any],
        knowledge_gaps: List[KnowledgeGap],
        iteration_number: int,
        max_queries: int = 10,
    ):
        """流式生成查询（返回 AgentEvent 迭代器）
        
        用于需要实时观察 Agent 推理过程的场景。
        """
        if self._react_agent is None:
            return

        user_message = self._build_user_message(
            research_topic, research_context, knowledge_gaps,
            iteration_number, max_queries,
            self._detect_language(research_topic),
        )

        async for event in self._react_agent.astream(user_message):
            yield event

    def generate_initial_queries(self, research_topic: str, num_queries: int = 3) -> str:
        """生成初始搜索查询的 Prompt（向后兼容）"""
        language = self._detect_language(research_topic)

        if language == "zh":
            return f"""
您是一位专业的搜索查询专家。请根据以下研究主题生成{num_queries}个高质量的搜索查询。

研究主题: {research_topic}

生成的查询应该：
1. 涵盖主题的不同方面
2. 使用不同的关键词组合
3. 包含具体和抽象的观点
4. 确保查询简洁且有针对性
5. 查询必须与研究主题使用相同的语言

请以JSON格式返回查询列表：
{{
    "queries": ["query1", "query2", "query3"]
}}
"""
        else:
            return f"""
You are a professional search query expert. Generate {num_queries} high-quality search queries for:

Research Topic: {research_topic}

Requirements:
1. Cover different aspects of the topic
2. Use varied keyword combinations
3. Include specific and abstract perspectives
4. Keep queries concise and targeted
5. Queries must match the language of the research topic

Return in JSON format:
{{
    "queries": ["query1", "query2", "query3"]
}}
"""

    def generate_followup_queries(
        self,
        research_topic: str,
        existing_findings: str,
        knowledge_gaps: str,
        num_queries: int = 3,
    ) -> str:
        """生成后续搜索查询 Prompt（向后兼容旧测试和旧工作流）。"""
        language = self._detect_language(research_topic)
        if language == "zh":
            return f"""
请基于已有研究发现和知识空白，为「{research_topic}」生成{num_queries}个后续搜索查询。

已有发现:
{existing_findings}

知识空白:
{knowledge_gaps}

请以JSON格式返回:
{{"queries": ["query1", "query2"]}}
"""
        return f"""
Generate {num_queries} follow-up search queries for "{research_topic}".

Existing findings:
{existing_findings}

Knowledge gaps:
{knowledge_gaps}

Return JSON:
{{"queries": ["query1", "query2"]}}
"""
    @property
    def query_stats(self) -> Dict[str, Any]:
        """获取查询统计"""
        return self._stats

    # ========================================================================
    # 内部方法
    # ========================================================================

    async def _generate_with_react_agent(
        self,
        topic: str,
        context: Dict[str, Any],
        gaps: List[KnowledgeGap],
        iteration: int,
        strategy: QueryStrategy,
        max_queries: int,
        language: str,
    ) -> List[str]:
        """使用 ReActAgent 生成查询"""
        user_message = self._build_user_message(
            topic, context, gaps, iteration, max_queries, language
        )

        try:
            result: ReActResult = await self._react_agent.arun(user_message)
            if result.success and result.output:
                return self._parse_queries_from_output(result.output)
        except Exception as e:
            logger.warning(f"[QueryGenerator] ReActAgent 生成失败，回退到工具直调: {e}")

        # 回退
        return self._generate_with_tool_directly(
            topic, gaps, strategy, max_queries, language
        )

    def _generate_with_tool_directly(
        self,
        topic: str,
        gaps: List[KnowledgeGap],
        strategy: QueryStrategy,
        max_queries: int,
        language: str,
    ) -> List[str]:
        """直接调用工具生成查询（无 LLM 回退）"""
        gap_texts = [g.topic for g in gaps] if gaps else None
        result_json = self._query_tool._run(
            topic=topic,
            strategy=strategy.value,
            max_queries=max_queries,
            knowledge_gaps=gap_texts,
            language=language,
        )
        try:
            parsed = json.loads(result_json)
            return parsed.get("queries", [])
        except json.JSONDecodeError:
            return []

    def _build_user_message(
        self,
        topic: str,
        context: Dict[str, Any],
        gaps: List[KnowledgeGap],
        iteration: int,
        max_queries: int,
        language: str,
    ) -> str:
        """构建发送给 ReActAgent 的用户消息"""
        previous_queries = context.get("previous_queries", [])
        gaps_text = "\n".join(f"- {g.topic}: {g.description}" for g in gaps) if gaps else "暂无"
        strategy = self._determine_strategy(iteration, gaps)

        if language == "zh":
            return f"""请为以下研究生成 {max_queries} 个高质量搜索查询。

研究主题: {topic}
推荐策略: {strategy.value}
迭代轮次: 第{iteration}轮
知识空白:
{gaps_text}

已有查询（避免重复）:
{chr(10).join(f'- {q}' for q in previous_queries[-10:]) if previous_queries else '暂无'}

请使用 generate_search_queries 工具生成查询，然后返回最终的查询列表。
"""
        else:
            return f"""Generate {max_queries} high-quality search queries for this research.

Topic: {topic}
Recommended Strategy: {strategy.value}
Iteration: {iteration}
Knowledge Gaps:
{gaps_text}

Previous queries (avoid duplicates):
{chr(10).join(f'- {q}' for q in previous_queries[-10:]) if previous_queries else 'None'}

Use the generate_search_queries tool and return the final query list.
"""

    def _parse_queries_from_output(self, output: str) -> List[str]:
        """从 ReActAgent 输出中解析查询列表"""
        # 尝试直接 JSON 解析
        try:
            parsed = json.loads(output)
            if isinstance(parsed, dict) and "queries" in parsed:
                return [q for q in parsed["queries"] if isinstance(q, str) and q.strip()]
        except json.JSONDecodeError:
            pass

        # 尝试从文本中提取 JSON
        import re
        json_match = re.search(r"\{[\s\S]*\}", output)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                if isinstance(parsed, dict) and "queries" in parsed:
                    return [q for q in parsed["queries"] if isinstance(q, str) and q.strip()]
            except json.JSONDecodeError:
                pass

        # 尝试按行解析
        lines = [l.strip().lstrip("- ").lstrip("* ") for l in output.split("\n") if l.strip()]
        return [l for l in lines if len(l) > 3 and not l.startswith("{")]

    def _determine_strategy(
        self, iteration: int, gaps: List[KnowledgeGap]
    ) -> QueryStrategy:
        """根据迭代轮次和知识空白确定策略"""
        if iteration == 1:
            return QueryStrategy.BROAD_EXPLORATION
        elif gaps and len(gaps) > 3:
            return QueryStrategy.GAP_FILLING
        elif iteration <= 3:
            return QueryStrategy.FOCUSED_DEEP_DIVE
        elif iteration <= 5:
            return QueryStrategy.MULTI_PERSPECTIVE
        else:
            return QueryStrategy.VERIFICATION

    def _infer_query_type(self, iteration: int, strategy: QueryStrategy) -> QueryType:
        """推断查询类型"""
        if iteration == 1:
            return QueryType.INITIAL
        elif strategy == QueryStrategy.GAP_FILLING:
            return QueryType.DEEP_DIVE
        elif strategy == QueryStrategy.VERIFICATION:
            return QueryType.CLARIFICATION
        else:
            return QueryType.FOLLOWUP

    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "zh" if chinese_chars > len(text) * 0.3 else "en"
