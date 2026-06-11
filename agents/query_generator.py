"""
Query Generator Agent

基于 AgenticX 框架的查询生成智能体。
负责根据研究主题、上下文和知识空白生成高质量的搜索查询。
"""

import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import Field

from agenticx.core.agent import Agent, AgentContext, AgentResult
from agenticx.llms.base import BaseLLMProvider

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
# Query Generator Agent
# ============================================================================

class QueryGeneratorAgent(Agent):
    """查询生成智能体
    
    基于 agenticx.core.agent.Agent 实现，提供：
    1. 智能查询生成（基于 LLM）
    2. 多策略查询优化
    3. 知识空白导向查询
    4. 查询质量评估
    5. 多语言查询支持
    """

    def __init__(
        self,
        name: str = "查询生成专家",
        role: str = "搜索查询策略师",
        goal: str = "生成高质量、多样化的搜索查询以支持深度研究",
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
                "你是一位经验丰富的搜索查询专家，擅长根据研究主题和上下文生成精确且多样化的搜索查询。"
                "你精通各种搜索策略，能够识别知识空白并制定相应的查询计划。"
            ),
            **kwargs
        )

        # 使用 object.__setattr__ 绕过 Pydantic 验证存储运行时状态
        object.__setattr__(self, "llm", llm_provider)
        object.__setattr__(self, "generated_queries_cache", set())
        object.__setattr__(self, "query_stats", {
            "total_generated": 0,
            "strategies_used": {},
        })

        # 查询模板
        object.__setattr__(self, "query_templates", {
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
        })

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

        # 使用 LLM 生成查询（如果可用）
        if self.llm is not None:
            queries = await self._generate_with_llm(
                research_topic, research_context, knowledge_gaps,
                iteration_number, strategy, max_queries, language
            )
        else:
            # 回退到模板生成
            queries = self._generate_from_templates(
                research_topic, knowledge_gaps, strategy, max_queries, language
            )

        # 去重
        unique_queries = self._deduplicate(queries)

        # 转换为 SearchQuery 模型
        search_queries = []
        for q_text in unique_queries[:max_queries]:
            sq = SearchQuery(
                query=q_text,
                query_type=self._infer_query_type(iteration_number, strategy),
                language="zh-CN" if language == "zh" else "en-US",
                max_results=10,
                search_engines=[SearchEngine.BOCHAAI],
            )
            search_queries.append(sq)

        # 更新统计
        stats = self.query_stats
        stats["total_generated"] += len(search_queries)
        stats["strategies_used"][strategy.value] = stats["strategies_used"].get(strategy.value, 0) + 1

        return search_queries

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

    # ========================================================================
    # 内部方法
    # ========================================================================

    async def _generate_with_llm(
        self,
        topic: str,
        context: Dict[str, Any],
        gaps: List[KnowledgeGap],
        iteration: int,
        strategy: QueryStrategy,
        max_queries: int,
        language: str,
    ) -> List[str]:
        """使用 LLM 生成查询"""
        previous_queries = context.get("previous_queries", [])
        gaps_text = "\n".join(f"- {g.topic}: {g.description}" for g in gaps) if gaps else "暂无"

        if language == "zh":
            prompt = f"""你是一位搜索查询生成专家。请根据以下信息生成{max_queries}个高质量搜索查询。

研究主题: {topic}
当前策略: {strategy.value}
迭代轮次: 第{iteration}轮
知识空白:
{gaps_text}

已有查询（避免重复）:
{chr(10).join(f'- {q}' for q in previous_queries[-10:]) if previous_queries else '暂无'}

要求：
1. 查询应多样化，覆盖不同角度
2. 避免与已有查询重复
3. 针对知识空白生成补充查询
4. 查询简洁精确，适合搜索引擎

请以JSON格式返回：
{{"queries": ["query1", "query2", ...]}}
"""
        else:
            prompt = f"""You are a search query generation expert. Generate {max_queries} high-quality queries.

Research Topic: {topic}
Strategy: {strategy.value}
Iteration: {iteration}
Knowledge Gaps:
{gaps_text}

Previous queries (avoid duplicates):
{chr(10).join(f'- {q}' for q in previous_queries[-10:]) if previous_queries else 'None'}

Requirements:
1. Diverse queries covering different angles
2. Avoid duplicating previous queries
3. Generate gap-filling queries
4. Concise and search-engine friendly

Return in JSON: {{"queries": ["query1", "query2", ...]}}
"""

        try:
            # 使用新的 invoke/ainvoke 接口
            response = await self.llm.ainvoke(prompt)
            response_text = response.content if hasattr(response, "content") else str(response)
            parsed = self._extract_json(response_text)
            queries = parsed.get("queries", [])
            return [q for q in queries if isinstance(q, str) and q.strip()]
        except Exception as e:
            logger.warning(f"[QueryGenerator] LLM 生成失败，回退到模板: {e}")
            return self._generate_from_templates(topic, gaps, strategy, max_queries, language)

    def _generate_from_templates(
        self,
        topic: str,
        gaps: List[KnowledgeGap],
        strategy: QueryStrategy,
        max_queries: int,
        language: str,
    ) -> List[str]:
        """基于模板生成查询"""
        queries = []
        templates = self.query_templates.get(strategy, [])

        for template in templates:
            try:
                gap_area = gaps[0].topic if gaps else "核心问题"
                alternative = "替代方案"
                query = template.format(
                    topic=topic,
                    gap_area=gap_area,
                    alternative=alternative,
                )
                queries.append(query)
            except (KeyError, IndexError):
                queries.append(template.replace("{topic}", topic))

        return queries[:max_queries]

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

    def _deduplicate(self, queries: List[str]) -> List[str]:
        """查询去重"""
        seen = set()
        unique = []
        cache: set = self.generated_queries_cache
        for q in queries:
            normalized = q.strip().lower()
            if normalized not in seen and normalized not in cache:
                seen.add(normalized)
                cache.add(normalized)
                unique.append(q.strip())
        return unique

    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "zh" if chinese_chars > len(text) * 0.3 else "en"

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """从 LLM 响应中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 块
        import re
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return {"queries": []}
