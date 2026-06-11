"""
Search Analyzer Agent

基于 AgenticX 框架的搜索结果分析智能体。
负责评估搜索结果质量、识别信息空白、评分搜索策略有效性。
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agenticx.core.agent import Agent, AgentContext, AgentResult
from agenticx.llms.base import BaseLLMProvider

from models import ResearchContext, KnowledgeGap, KnowledgeItem

logger = logging.getLogger(__name__)


class SearchAnalyzerAgent(Agent):
    """搜索结果分析智能体
    
    基于 agenticx.core.Agent 实现，负责：
    1. 分析搜索结果质量和相关性
    2. 提取关键知识项
    3. 识别信息空白
    4. 评估搜索策略有效性
    """

    def __init__(
        self,
        name: str = "搜索分析专家",
        role: str = "信息分析与评估师",
        goal: str = "深入分析搜索结果，提取关键知识，识别信息空白",
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
                "你是一位经验丰富的信息分析专家，擅长从大量搜索结果中提取关键信息、"
                "评估信息质量、识别知识空白，并为后续研究提供方向指引。"
            ),
            **kwargs
        )

        object.__setattr__(self, "llm", llm_provider)

    # ========================================================================
    # 公共接口
    # ========================================================================

    async def analyze_search_results(
        self,
        search_results: List[Dict[str, Any]],
        research_topic: str,
        research_objective: str = "",
    ) -> Dict[str, Any]:
        """分析搜索结果
        
        Args:
            search_results: 搜索结果列表（统一 dict 格式）
            research_topic: 研究主题
            research_objective: 研究目标
            
        Returns:
            分析结果字典
        """
        language = self._detect_language(research_topic)
        results_text = self._format_results(search_results)

        if language == "zh":
            prompt = f"""你是一位信息分析专家。请分析以下搜索结果。

研究主题: {research_topic}
研究目标: {research_objective or '全面了解该主题'}

搜索结果:
{results_text}

请从以下维度分析：
1. 整体质量评估（信息源权威性、准确性、时效性）
2. 相关性分析（与研究主题的匹配度）
3. 完整性评估（覆盖的知识领域、缺失的信息）
4. 信息质量分类（高/中/低质量）

以JSON格式返回：
{{
    "summary": "整体分析摘要",
    "key_findings": ["发现1", "发现2"],
    "knowledge_items": [
        {{"content": "知识内容", "type": "fact", "confidence": 8.0, "source": "URL"}}
    ],
    "quality_score": 7.5,
    "relevance_score": 8.0,
    "completeness_score": 6.5,
    "coverage_assessment": "覆盖度评估",
    "reliability_notes": "可靠性说明"
}}
"""
        else:
            prompt = f"""You are an information analysis expert. Analyze these search results.

Topic: {research_topic}
Objective: {research_objective or 'Comprehensive understanding'}

Results:
{results_text}

Analyze from these dimensions:
1. Overall quality (authority, accuracy, timeliness)
2. Relevance (match with research topic)
3. Completeness (coverage, missing info)
4. Quality classification (high/medium/low)

Return JSON:
{{
    "summary": "overall summary",
    "key_findings": ["finding1", "finding2"],
    "knowledge_items": [
        {{"content": "knowledge", "type": "fact", "confidence": 8.0, "source": "url"}}
    ],
    "quality_score": 7.5,
    "relevance_score": 8.0,
    "completeness_score": 6.5,
    "coverage_assessment": "coverage assessment",
    "reliability_notes": "reliability notes"
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
                logger.warning(f"[SearchAnalyzer] LLM 分析失败: {e}")

        # 回退：基础分析
        return {
            "summary": f"共获得 {len(search_results)} 条搜索结果",
            "key_findings": [],
            "knowledge_items": [],
            "quality_score": 5.0,
            "relevance_score": 5.0,
            "completeness_score": 5.0,
            "coverage_assessment": "待评估",
            "reliability_notes": "需要进一步验证",
        }

    async def identify_information_gaps(
        self,
        research_context: ResearchContext,
        analysis_result: Optional[Dict[str, Any]] = None,
    ) -> List[KnowledgeGap]:
        """识别信息空白
        
        Args:
            research_context: 研究上下文
            analysis_result: 搜索分析结果（可选）
            
        Returns:
            KnowledgeGap 列表
        """
        language = self._detect_language(research_context.research_topic)
        
        # 汇总当前发现
        current_findings = []
        for iteration in research_context.iterations:
            if iteration.analysis_summary:
                current_findings.append(iteration.analysis_summary)
        findings_text = "\n".join(f"- {f}" for f in current_findings) if current_findings else "暂无"

        if language == "zh":
            prompt = f"""你是信息空白识别专家。请根据以下信息识别研究中的空白。

研究主题: {research_context.research_topic}
研究目标: {research_context.research_objective}
当前发现: {findings_text}
搜索结果数: {len(research_context.get_all_search_results())}

请识别以下类型的信息空白：
- 核心概念空白
- 技术细节空白
- 应用案例空白
- 比较分析空白
- 最新发展空白

以JSON返回：
{{
    "gaps": [
        {{
            "topic": "空白主题",
            "description": "详细描述",
            "priority": 7,
            "suggested_queries": ["建议查询1", "建议查询2"]
        }}
    ]
}}
"""
        else:
            prompt = f"""You are an information gap expert. Identify research gaps.

Topic: {research_context.research_topic}
Objective: {research_context.research_objective}
Findings: {findings_text}
Results Count: {len(research_context.get_all_search_results())}

Identify gaps (core concepts, technical details, applications, comparisons, latest developments):

Return JSON:
{{
    "gaps": [
        {{
            "topic": "gap topic",
            "description": "description",
            "priority": 7,
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
                return [
                    KnowledgeGap(
                        topic=g.get("topic", ""),
                        description=g.get("description", ""),
                        priority=g.get("priority", 5),
                        suggested_queries=g.get("suggested_queries", []),
                        identified_by=self.name,
                    )
                    for g in parsed.get("gaps", [])
                    if g.get("topic")
                ]
            except Exception as e:
                logger.warning(f"[SearchAnalyzer] 空白识别失败: {e}")

        return []

    async def evaluate_search_strategy(
        self,
        research_context: ResearchContext,
        iteration_results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """评估搜索策略有效性
        
        Returns:
            策略评估结果
        """
        language = self._detect_language(research_context.research_topic)
        num_results = len(research_context.get_all_search_results())
        
        # 构建搜索历史摘要
        search_history = []
        for iteration in research_context.iterations:
            for query in iteration.queries:
                search_history.append(query.query)

        if language == "zh":
            prompt = f"""评估当前搜索策略的有效性。

研究主题: {research_context.research_topic}
迭代轮次: {research_context.current_iteration}
总结果数: {num_results}
搜索历史: {json.dumps(search_history[-10:], ensure_ascii=False)}

请从查询多样性、搜索深度、覆盖广度、结果质量、效率等方面评估。

以JSON返回：
{{
    "effectiveness_score": 7.0,
    "diversity_score": 6.5,
    "depth_score": 7.0,
    "coverage_score": 6.0,
    "recommendations": ["建议1", "建议2"],
    "issues": ["问题1"],
    "next_directions": ["方向1", "方向2"]
}}
"""
        else:
            prompt = f"""Evaluate search strategy effectiveness.

Topic: {research_context.research_topic}
Iteration: {research_context.current_iteration}
Total Results: {num_results}
Search History: {json.dumps(search_history[-10:], ensure_ascii=False)}

Evaluate diversity, depth, coverage, quality, efficiency.

Return JSON:
{{
    "effectiveness_score": 7.0,
    "diversity_score": 6.5,
    "depth_score": 7.0,
    "coverage_score": 6.0,
    "recommendations": ["rec1", "rec2"],
    "issues": ["issue1"],
    "next_directions": ["dir1", "dir2"]
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
                logger.warning(f"[SearchAnalyzer] 策略评估失败: {e}")

        return {
            "effectiveness_score": 5.0,
            "diversity_score": 5.0,
            "depth_score": 5.0,
            "coverage_score": 5.0,
            "recommendations": ["增加搜索多样性"],
            "issues": [],
            "next_directions": ["深入探索"],
        }

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _format_results(self, results: List[Dict[str, Any]]) -> str:
        """格式化搜索结果为文本"""
        lines = []
        for i, r in enumerate(results[:15], 1):
            if isinstance(r, dict):
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("snippet", "")
            else:
                title = getattr(r, "title", "")
                url = getattr(r, "url", "")
                snippet = getattr(r, "snippet", "")
            lines.append(f"{i}. [{title}]({url})\n   {snippet[:150]}")
        return "\n".join(lines) if lines else "暂无结果"

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
