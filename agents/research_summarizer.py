"""
Research Summarizer Agent (v2 - ReActAgent Based)

基于 AgenticX ReActAgent 异步版本的研究总结智能体。
利用原生 function calling 能力，自主调用搜索工具执行搜索、总结和反思。
支持流式事件输出，实现完整的 Search → Summarize → Reflect 循环。
"""

import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

from agenticx.agents.react_agent_async import ReActAgent, ReActResult
from agenticx.agents.agent_events import AgentEvent, FinalEvent
from agenticx.llms.base import BaseLLMProvider
from agenticx.tools.base import BaseTool

logger = logging.getLogger(__name__)


# ============================================================================
# Research Summarizer Agent (ReActAgent Wrapper)
# ============================================================================

class ResearchSummarizerAgent:
    """研究总结智能体 (v2 - ReActAgent Based)
    
    基于 agenticx.agents.ReActAgent 异步版本实现：
    1. 原生 function calling - 自主调用搜索工具
    2. 流式事件输出 (astream) - 实时观察推理过程
    3. 循环检测 - 避免无效重复搜索
    4. 多角色切换 - 搜索总结 / 反思 / 报告撰写
    
    Usage:
        agent = ResearchSummarizerAgent(
            llm_provider=my_llm,
            search_tools=[bochaai_tool, google_tool],
        )
        
        # 搜索并总结
        summary = await agent.search_and_summarize(
            query="人工智能最新进展",
            research_topic="AI发展趋势",
        )
        
        # 反思
        reflection = await agent.reflect(
            research_topic="AI发展趋势",
            current_summary=summary,
            iteration_number=1,
        )
        
        # 生成最终报告
        report = await agent.generate_final_report(
            research_topic="AI发展趋势",
            all_summaries="...",
            citations="...",
        )
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        search_tools: Optional[Sequence[BaseTool]] = None,
        max_iterations: int = 10,
        **kwargs,
    ):
        self.llm = llm_provider
        self._search_tools = list(search_tools) if search_tools else []
        self._max_iterations = max_iterations

        # 构建不同角色的 ReActAgent
        self._search_agent: Optional[ReActAgent] = None
        self._reflection_agent: Optional[ReActAgent] = None
        self._report_agent: Optional[ReActAgent] = None

        if self.llm is not None:
            # 搜索与总结 Agent（配备搜索工具）
            self._search_agent = ReActAgent(
                llm=self.llm,
                tools=self._search_tools,
                system_prompt=self._search_system_prompt(),
                max_iterations=self._max_iterations,
            )

            # 反思 Agent（无工具，纯推理）
            self._reflection_agent = ReActAgent(
                llm=self.llm,
                tools=[],
                system_prompt=self._reflection_system_prompt(),
                max_iterations=3,
            )

            # 报告撰写 Agent（无工具，纯推理）
            self._report_agent = ReActAgent(
                llm=self.llm,
                tools=[],
                system_prompt=self._report_system_prompt(),
                max_iterations=3,
            )

    # ========================================================================
    # 公共接口
    # ========================================================================

    async def search_and_summarize(
        self,
        query: str,
        research_topic: str,
    ) -> str:
        """执行搜索并总结结果
        
        Args:
            query: 搜索查询
            research_topic: 研究主题
            
        Returns:
            总结文本
        """
        if self._search_agent is None:
            return f"[无 LLM] 搜索查询: {query}"

        language = self._detect_language(research_topic)
        user_message = self._build_search_message(query, research_topic, language)

        try:
            result: ReActResult = await self._search_agent.arun(user_message)
            if result.success and result.output:
                return result.output
            return f"搜索完成但未获得有效总结 (iterations={result.iterations})"
        except Exception as e:
            logger.warning(f"[ResearchSummarizer] 搜索总结失败: {e}")
            return f"搜索总结失败: {str(e)}"

    async def search_and_summarize_stream(
        self,
        query: str,
        research_topic: str,
    ) -> AsyncIterator[AgentEvent]:
        """流式执行搜索并总结（返回 AgentEvent 迭代器）"""
        if self._search_agent is None:
            return

        language = self._detect_language(research_topic)
        user_message = self._build_search_message(query, research_topic, language)

        async for event in self._search_agent.astream(user_message):
            yield event

    async def reflect(
        self,
        research_topic: str,
        current_summary: str,
        iteration_number: int,
    ) -> Dict[str, Any]:
        """对当前研究进展进行反思
        
        Args:
            research_topic: 研究主题
            current_summary: 当前摘要
            iteration_number: 迭代轮次
            
        Returns:
            反思结果字典
        """
        if self._reflection_agent is None:
            return self._default_reflection()

        language = self._detect_language(research_topic)
        user_message = self._build_reflection_message(
            research_topic, current_summary, iteration_number, language
        )

        try:
            result: ReActResult = await self._reflection_agent.arun(user_message)
            if result.success and result.output:
                return self._parse_reflection(result.output)
        except Exception as e:
            logger.warning(f"[ResearchSummarizer] 反思失败: {e}")

        return self._default_reflection()

    async def generate_final_report(
        self,
        research_topic: str,
        all_summaries: str,
        citations: str,
    ) -> str:
        """生成最终研究报告
        
        Args:
            research_topic: 研究主题
            all_summaries: 所有摘要汇总
            citations: 引用来源
            
        Returns:
            最终报告文本
        """
        if self._report_agent is None:
            return f"# {research_topic}\n\n{all_summaries}\n\n## 参考文献\n{citations}"

        language = self._detect_language(research_topic)
        user_message = self._build_report_message(
            research_topic, all_summaries, citations, language
        )

        try:
            result: ReActResult = await self._report_agent.arun(user_message)
            if result.success and result.output:
                return result.output
        except Exception as e:
            logger.warning(f"[ResearchSummarizer] 报告生成失败: {e}")

        return f"# {research_topic}\n\n{all_summaries}\n\n## 参考文献\n{citations}"

    # ========================================================================
    # 向后兼容 Prompt 接口
    # ========================================================================

    def create_search_and_summarize_prompt(
        self, query: str, research_topic: str
    ) -> str:
        """创建搜索与总结 Prompt（向后兼容）"""
        language = self._detect_language(research_topic)
        return self._build_search_message(query, research_topic, language)

    def create_reflection_prompt(
        self,
        research_topic: str,
        current_summary: str,
        iteration_number: int,
    ) -> str:
        """创建反思 Prompt（向后兼容）"""
        language = self._detect_language(research_topic)
        return self._build_reflection_message(
            research_topic, current_summary, iteration_number, language
        )

    def create_final_report_prompt(
        self,
        research_topic: str,
        all_summaries: str,
        citations: str,
    ) -> str:
        """创建最终报告 Prompt（向后兼容）"""
        language = self._detect_language(research_topic)
        return self._build_report_message(
            research_topic, all_summaries, citations, language
        )

    # ========================================================================
    # System Prompts
    # ========================================================================

    def _search_system_prompt(self) -> str:
        return """你是一位专业的研究分析师，擅长搜索信息并生成结构化摘要。

你的工作流程：
1. 使用搜索工具搜索给定查询
2. 分析搜索结果，提取关键信息
3. 生成结构化摘要，包含关键发现和来源引用

摘要格式要求：
- 简洁明了，突出重要信息
- 包含具体事实和数据
- 注明信息来源 URL
- 识别潜在的偏见或不确定性

如果搜索结果不充分，可以尝试使用不同的查询重新搜索。
最终以清晰的段落格式输出摘要。
"""

    def _reflection_system_prompt(self) -> str:
        return """你是一位研究反思专家，擅长评估研究进展的完整性和质量。

你的任务是对当前研究进展进行批判性反思，评估：
1. 信息完整性 - 是否覆盖了主题的各个方面
2. 知识空白 - 是否存在明显的信息缺失
3. 来源多样性 - 信息来源是否足够多样
4. 证据充分性 - 结论是否有充分证据支撑
5. 下一步建议 - 应该从哪些方向补充信息

请以 JSON 格式输出反思结果（不要 markdown 代码块）：
{"completeness_score": 0.0-1.0, "identified_gaps": [...], "suggested_next_queries": [...], "confidence_level": "high/medium/low", "reflection_summary": "..."}
"""

    def _report_system_prompt(self) -> str:
        return """你是一位研究报告撰写专家，擅长将研究发现组织为专业的研究报告。

报告结构要求：
1. 标题
2. 摘要（200-300字）
3. 引言（研究背景和目标）
4. 主要发现（分点详述）
5. 分析与讨论
6. 结论与建议
7. 参考文献

报告质量要求：
- 内容准确，逻辑清晰
- 适当引用来源（使用[数字]格式）
- 语言专业，结构完整
- 总字数 1500-3000 字
"""

    # ========================================================================
    # Message Builders
    # ========================================================================

    def _build_search_message(self, query: str, topic: str, language: str) -> str:
        if language == "zh":
            return f"""请执行以下搜索查询并总结结果：

搜索查询: {query}
研究主题: {topic}

请搜索此查询，分析结果，提取关键信息，并创建结构化摘要。
"""
        else:
            return f"""Execute the following search query and summarize results:

Search Query: {query}
Research Topic: {topic}

Search for this query, analyze results, extract key information, and create a structured summary.
"""

    def _build_reflection_message(
        self, topic: str, summary: str, iteration: int, language: str
    ) -> str:
        if language == "zh":
            return f"""请对当前研究进展进行反思。

研究主题: {topic}
当前迭代: 第{iteration}轮
当前摘要:
{summary}

请评估信息完整性、识别知识空白、建议下一步查询。
以 JSON 格式输出反思结果。
"""
        else:
            return f"""Reflect on current research progress.

Topic: {topic}
Iteration: {iteration}
Current Summary:
{summary}

Evaluate completeness, identify gaps, suggest next queries.
Output reflection in JSON format.
"""

    def _build_report_message(
        self, topic: str, summaries: str, citations: str, language: str
    ) -> str:
        if language == "zh":
            return f"""请基于以下研究摘要撰写最终研究报告。

研究主题: {topic}

研究摘要汇总:
{summaries}

引用来源:
{citations}

请撰写一份完整的研究报告。
"""
        else:
            return f"""Write a final research report based on the following summaries.

Topic: {topic}

Research Summaries:
{summaries}

Citations:
{citations}

Write a complete research report.
"""

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _parse_reflection(self, output: str) -> Dict[str, Any]:
        """解析反思输出"""
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r"\{[\s\S]*\}", output)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        return self._default_reflection()

    def _default_reflection(self) -> Dict[str, Any]:
        """默认反思结果"""
        return {
            "completeness_score": 0.5,
            "identified_gaps": [],
            "suggested_next_queries": [],
            "confidence_level": "low",
            "reflection_summary": "需要更多信息",
        }

    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        return "zh" if chinese_chars > len(text) * 0.3 else "en"
