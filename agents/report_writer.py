"""
Report Writer Agent

基于 AgenticX 框架的报告撰写智能体。
负责将研究发现整合为结构化的研究报告。
"""

import json
import logging
import asyncio
import os
import re
from typing import Any, Dict, List, Optional

from agenticx.core.agent import Agent, AgentContext, AgentResult
from agenticx.llms.base import BaseLLMProvider

from token_budget import TokenBudget
from models import (
    ResearchContext,
    ResearchReport,
    ReportSection,
    Citation,
)

logger = logging.getLogger(__name__)


class ReportWriterAgent(Agent):
    """报告撰写智能体
    
    基于 agenticx.core.Agent 实现，负责：
    1. 生成报告大纲
    2. 撰写报告摘要
    3. 撰写各章节内容
    4. 整合引用和参考文献
    5. 生成完整研究报告
    """

    def __init__(
        self,
        name: str = "报告撰写专家",
        role: str = "研究报告撰写师",
        goal: str = "将研究发现整合为高质量、结构化的研究报告",
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
                "你是一位经验丰富的研究报告撰写专家，擅长将复杂的研究发现"
                "整合为清晰、结构化、有引用支撑的专业研究报告。"
            ),
            **kwargs
        )

        object.__setattr__(self, "llm", llm_provider)

    # ========================================================================
    # 公共接口
    # ========================================================================

    async def generate_report(
        self,
        research_context: ResearchContext,
    ) -> ResearchReport:
        """生成完整研究报告（主入口）
        
        Args:
            research_context: 研究上下文（包含所有迭代结果）
            
        Returns:
            ResearchReport 实例
        """
        if os.getenv("FAST_CLI", "1") == "1":
            return await self._generate_fast_report(research_context)

        # 1. 生成大纲
        outline = await self.generate_report_outline(research_context)

        # 2. 撰写摘要
        abstract = await self.write_abstract(research_context, outline)

        # 3. 撰写各章节
        sections = []
        for section_info in outline.get("sections", []):
            section = await self.write_section(research_context, section_info)
            sections.append(section)

        # 4. 收集引用
        citations = self._collect_citations(research_context)

        # 5. 组装报告
        report = ResearchReport(
            title=outline.get("title", research_context.research_topic),
            abstract=abstract,
            sections=sections,
            citations=citations,
            metadata={
                "topic": research_context.research_topic,
                "iterations": research_context.current_iteration,
                "total_results": len(research_context.get_all_search_results()),
            },
        )

        return report

    async def _generate_fast_report(self, research_context: ResearchContext) -> ResearchReport:
        """Generate a concise report with one bounded LLM call for CLI usage."""
        findings = self._extract_key_findings(research_context)
        sources = self._format_sources(research_context)
        budget = TokenBudget(max_tokens=1800)
        findings_context = budget.truncate(findings)
        sources_context = budget.truncate(sources, max_tokens=700)
        prompt = f"""请基于已有研究摘要生成一份简洁但可读的中文研究报告。

研究主题: {research_context.research_topic}
研究目标: {research_context.research_objective}
研究摘要:
{findings_context}

来源线索:
{sources_context}

要求:
1. 必须先检查用户问题中的事实前提是否被证据支持。
2. 如果“收购 Cursor”等前提没有可靠证据，必须明确写为“未能证实”，不要当作事实展开。
3. 报告结构包含：核心结论、主要影响面、对 Cursor 的可能影响、风险与不确定性、后续需要核验的信息。
4. 控制在 1200-1800 字。
"""
        content = ""
        if self.llm:
            try:
                response = await asyncio.wait_for(
                    self.llm.ainvoke(prompt),
                    timeout=float(os.getenv("LLM_TIMEOUT", "45")),
                )
                content = (response.content if hasattr(response, "content") else str(response)).strip()
            except Exception as e:
                logger.warning(f"[ReportWriter] 快速报告生成失败: {e}")

        if not content:
            content = f"## 核心发现\n\n{findings_context or '暂无有效发现。'}\n\n## 来源线索\n\n{sources_context or '暂无来源。'}"

        abstract = (
            f"本报告围绕「{research_context.research_topic}」进行快速研究。"
            "报告优先呈现已获得证据，并标注未能证实的前提与不确定性。"
        )
        return ResearchReport(
            title=f"{research_context.research_topic} 研究报告",
            abstract=abstract,
            sections=[
                ReportSection(
                    title="快速研究报告",
                    content=content,
                    level=1,
                )
            ],
            citations=self._collect_citations(research_context),
            metadata={
                "topic": research_context.research_topic,
                "iterations": research_context.current_iteration,
                "mode": "fast",
            },
        )

    async def generate_report_outline(
        self,
        research_context: ResearchContext,
    ) -> Dict[str, Any]:
        """生成报告大纲"""
        language = self._detect_language(research_context.research_topic)
        findings = self._extract_key_findings(research_context)

        if language == "zh":
            prompt = f"""你是研究报告结构专家。请为以下研究生成报告大纲。

研究主题: {research_context.research_topic}
研究目标: {research_context.research_objective}
迭代轮次: {research_context.current_iteration}
关键发现摘要: {findings[:2000]}

请生成报告大纲，以JSON返回：
{{
    "title": "报告标题",
    "sections": [
        {{"title": "章节标题", "level": 1, "focus": "章节重点", "subsections": ["子节1", "子节2"]}}
    ]
}}
"""
        else:
            prompt = f"""You are a report structure expert. Generate an outline.

Topic: {research_context.research_topic}
Objective: {research_context.research_objective}
Iterations: {research_context.current_iteration}
Key Findings: {findings[:2000]}

Generate outline in JSON:
{{
    "title": "Report Title",
    "sections": [
        {{"title": "Section Title", "level": 1, "focus": "focus area", "subsections": ["sub1", "sub2"]}}
    ]
}}
"""

        if self.llm:
            try:
                response = await self.llm.ainvoke(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                result = self._extract_json(text)
                if result and "sections" in result:
                    return result
            except Exception as e:
                logger.warning(f"[ReportWriter] 大纲生成失败: {e}")

        # 默认大纲
        return {
            "title": f"{research_context.research_topic} 研究报告",
            "sections": [
                {"title": "引言", "level": 1, "focus": "背景介绍", "subsections": []},
                {"title": "研究方法", "level": 1, "focus": "方法论", "subsections": []},
                {"title": "主要发现", "level": 1, "focus": "核心结果", "subsections": []},
                {"title": "分析与讨论", "level": 1, "focus": "深入分析", "subsections": []},
                {"title": "结论与展望", "level": 1, "focus": "总结", "subsections": []},
            ],
        }

    async def write_abstract(
        self,
        research_context: ResearchContext,
        outline: Dict[str, Any],
    ) -> str:
        """撰写报告摘要"""
        language = self._detect_language(research_context.research_topic)
        findings = self._extract_key_findings(research_context)

        if language == "zh":
            prompt = f"""请为以下研究报告撰写摘要（200-400字）。

报告标题: {outline.get('title', research_context.research_topic)}
研究主题: {research_context.research_topic}
研究目标: {research_context.research_objective}
关键发现: {findings[:1500]}

摘要应包含：研究背景、方法、主要发现、结论。
请直接输出摘要文本。
"""
        else:
            prompt = f"""Write an abstract (200-400 words) for this research report.

Title: {outline.get('title', research_context.research_topic)}
Topic: {research_context.research_topic}
Objective: {research_context.research_objective}
Key Findings: {findings[:1500]}

Include: background, methods, key findings, conclusions.
Output the abstract text directly.
"""

        if self.llm:
            try:
                response = await self.llm.ainvoke(prompt)
                text = response.content if hasattr(response, "content") else str(response)
                return text.strip()
            except Exception as e:
                logger.warning(f"[ReportWriter] 摘要撰写失败: {e}")

        return f"本报告对「{research_context.research_topic}」进行了系统性研究。"

    async def write_section(
        self,
        research_context: ResearchContext,
        section_info: Dict[str, Any],
    ) -> ReportSection:
        """撰写单个章节"""
        language = self._detect_language(research_context.research_topic)
        section_title = section_info.get("title", "")
        section_focus = section_info.get("focus", "")
        findings = self._extract_key_findings(research_context)
        sources = self._format_sources(research_context)
        section_budget = TokenBudget(max_tokens=900)
        findings_context = section_budget.truncate(findings)
        sources_context = section_budget.truncate(sources, max_tokens=450)

        if language == "zh":
            prompt = f"""请撰写研究报告的以下章节。

研究主题: {research_context.research_topic}
章节标题: {section_title}
章节重点: {section_focus}
相关发现: {findings_context}
信息来源: {sources_context}

要求：
1. 内容详实，有据可查
2. 逻辑清晰，层次分明
3. 适当引用来源（使用[数字]格式）
4. 300-800字

请直接输出章节内容。
"""
        else:
            prompt = f"""Write the following section of a research report.

Topic: {research_context.research_topic}
Section: {section_title}
Focus: {section_focus}
Findings: {findings_context}
Sources: {sources_context}

Requirements:
1. Well-supported content
2. Clear logical structure
3. Proper citations (use [number] format)
4. 300-800 words

Output the section content directly.
"""

        content = ""
        if self.llm:
            try:
                response = await self.llm.ainvoke(prompt)
                content = response.content if hasattr(response, "content") else str(response)
                content = content.strip()
            except Exception as e:
                logger.warning(f"[ReportWriter] 章节撰写失败: {e}")
                content = f"（{section_title}内容待补充）"

        # 构建子章节
        subsections = []
        for sub_title in section_info.get("subsections", []):
            if isinstance(sub_title, str):
                subsections.append(ReportSection(
                    title=sub_title,
                    content="",
                    level=2,
                ))
            elif isinstance(sub_title, dict):
                sub_section = await self.write_section(research_context, sub_title)
                subsections.append(sub_section)

        return ReportSection(
            title=section_title,
            content=content,
            level=section_info.get("level", 1),
            subsections=subsections,
        )

    # ========================================================================
    # 向后兼容接口
    # ========================================================================

    def generate_complete_report(self, research_context: ResearchContext) -> ResearchReport:
        """同步生成完整报告（向后兼容）"""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(
                    asyncio.run, self.generate_report(research_context)
                ).result()
        except RuntimeError:
            return asyncio.run(self.generate_report(research_context))

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _extract_key_findings(self, context: ResearchContext) -> str:
        """提取关键发现"""
        findings = []
        for iteration in context.iterations:
            if iteration.analysis_summary:
                findings.append(iteration.analysis_summary)
            for item in iteration.knowledge_items:
                findings.append(f"[{item.type}] {item.content}")
        
        if not findings and context.overall_findings:
            findings.append(context.overall_findings)

        # 从搜索结果中提取
        if not findings:
            for r in context.get_all_search_results()[:10]:
                if isinstance(r, dict):
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                else:
                    title = getattr(r, "title", "")
                    snippet = getattr(r, "snippet", "")
                if title:
                    findings.append(f"• {title}: {snippet[:100]}")

        return "\n".join(findings[:30]) if findings else "暂无"

    def _format_sources(self, context: ResearchContext) -> str:
        """格式化信息来源"""
        sources = []
        all_results = context.get_all_search_results()
        for i, r in enumerate(all_results[:20], 1):
            if isinstance(r, dict):
                title = r.get("title", "")
                url = r.get("url", "")
                snippet = r.get("snippet", "")
            else:
                title = getattr(r, "title", "")
                url = getattr(r, "url", "")
                snippet = getattr(r, "snippet", "")
            if title and url:
                sources.append(f"[{i}] {title}\n    来源: {url}\n    摘要: {snippet[:100]}")
        return "\n".join(sources) if sources else "暂无来源"

    def _collect_citations(self, context: ResearchContext) -> List[Citation]:
        """收集引用"""
        citations = []
        seen_urls = set()
        all_results = context.get_all_search_results()

        for r in all_results:
            if isinstance(r, dict):
                url = r.get("url", "")
                title = r.get("title", "")
            else:
                url = getattr(r, "url", "")
                title = getattr(r, "title", "")

            if url and url not in seen_urls:
                seen_urls.add(url)
                citations.append(Citation(
                    source_url=url,
                    title=title,
                ))

        return citations[:50]

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
