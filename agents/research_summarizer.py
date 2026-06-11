"""
Research Summarizer Agent

基于 AgenticX 框架的研究总结智能体。
负责执行搜索、总结结果、反思信息充分性。
"""

import logging
from typing import Any, Dict, List, Optional

from agenticx.core.agent import Agent, AgentContext, AgentResult
from agenticx.llms.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class ResearchSummarizerAgent(Agent):
    """研究总结智能体
    
    基于 agenticx.core.Agent 实现，负责：
    1. 搜索结果总结
    2. 信息充分性反思
    3. 最终报告摘要生成
    """

    def __init__(
        self,
        name: str = "首席研究分析师",
        role: str = "研究总结与反思专家",
        goal: str = "综合搜索信息，生成连贯摘要，识别知识空白，产出高质量研究报告",
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
                "你是一位细致入微的分析师，擅长快速处理大量信息、识别关键洞察，"
                "并将其组织为全面易懂的报告。你始终用引用支撑论点，"
                "并善于发现缺失的信息。"
            ),
            tool_names=["bochaai_web_search", "google_web_search"],
            **kwargs
        )

        object.__setattr__(self, "llm", llm_provider)

    # ========================================================================
    # Prompt 生成接口
    # ========================================================================

    def create_search_and_summarize_prompt(
        self, query: str, research_topic: str
    ) -> str:
        """创建搜索与总结 Prompt"""
        language = self._detect_language(research_topic)

        if language == "zh":
            return f"""
你是一位专业的研究分析师。请执行以下搜索查询并总结结果：

搜索查询: {query}
研究主题: {research_topic}

请按照以下步骤进行：
1. 使用搜索工具搜索此查询
2. 分析搜索结果
3. 提取关键信息和要点
4. 创建结构化摘要

摘要格式要求：
- 简洁明了，突出重要信息
- 包含具体事实和数据
- 注明信息来源
- 识别潜在的偏见或不确定性

请以清晰的段落格式输出摘要。
"""
        else:
            return f"""
You are a professional research analyst. Execute the following search query and summarize results:

Search Query: {query}
Research Topic: {research_topic}

Steps:
1. Use search tools to search for this query
2. Analyze the search results
3. Extract key information and main points
4. Create a structured summary

Summary requirements:
- Concise, highlighting important information
- Include specific facts and data
- Note information sources
- Identify potential biases or uncertainties

Output the summary in clear paragraph format.
"""

    def create_reflection_prompt(
        self,
        research_topic: str,
        current_summary: str,
        iteration_number: int,
    ) -> str:
        """创建反思 Prompt"""
        language = self._detect_language(research_topic)

        if language == "zh":
            return f"""
你是一位研究反思专家。请对当前研究进展进行反思。

研究主题: {research_topic}
当前迭代: 第{iteration_number}轮
当前摘要:
{current_summary}

请反思以下问题：
1. 当前信息是否足够全面？
2. 是否存在明显的知识空白？
3. 信息来源是否多样且可靠？
4. 是否需要从其他角度补充信息？
5. 当前结论是否有充分的证据支撑？

请以JSON格式输出反思结果：
{{
    "completeness_score": 0.0-1.0,
    "identified_gaps": ["空白1", "空白2"],
    "suggested_next_queries": ["建议查询1", "建议查询2"],
    "confidence_level": "high/medium/low",
    "reflection_summary": "反思总结"
}}
"""
        else:
            return f"""
You are a research reflection expert. Reflect on current research progress.

Topic: {research_topic}
Iteration: {iteration_number}
Current Summary:
{current_summary}

Reflect on:
1. Is the current information comprehensive enough?
2. Are there obvious knowledge gaps?
3. Are sources diverse and reliable?
4. Do we need information from other angles?
5. Are conclusions well-supported by evidence?

Output in JSON:
{{
    "completeness_score": 0.0-1.0,
    "identified_gaps": ["gap1", "gap2"],
    "suggested_next_queries": ["query1", "query2"],
    "confidence_level": "high/medium/low",
    "reflection_summary": "reflection summary"
}}
"""

    def create_final_report_prompt(
        self,
        research_topic: str,
        all_summaries: str,
        citations: str,
    ) -> str:
        """创建最终报告 Prompt"""
        language = self._detect_language(research_topic)

        if language == "zh":
            return f"""
你是一位研究报告撰写专家。请基于以下研究摘要撰写最终研究报告。

研究主题: {research_topic}

研究摘要汇总:
{all_summaries}

引用来源:
{citations}

请撰写一份完整的研究报告，包括：
1. 标题
2. 摘要（200-300字）
3. 引言（研究背景和目标）
4. 主要发现（分点详述）
5. 分析与讨论
6. 结论与建议
7. 参考文献

报告要求：
- 内容准确，逻辑清晰
- 适当引用来源（使用[数字]格式）
- 语言专业，结构完整
- 总字数 1500-3000 字
"""
        else:
            return f"""
You are a research report writing expert. Write a final research report.

Topic: {research_topic}

Research Summaries:
{all_summaries}

Citations:
{citations}

Write a complete report including:
1. Title
2. Abstract (200-300 words)
3. Introduction (background and objectives)
4. Key Findings (detailed points)
5. Analysis and Discussion
6. Conclusions and Recommendations
7. References

Requirements:
- Accurate content, clear logic
- Proper citations (use [number] format)
- Professional language, complete structure
- Total 1500-3000 words
"""

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "zh" if chinese_chars > len(text) * 0.3 else "en"
