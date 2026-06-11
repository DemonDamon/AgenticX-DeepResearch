"""
AgenticX-DeepResearch 核心数据模型

本模块定义了深度搜索系统中使用的核心数据结构。
全部采用 Pydantic BaseModel，与 AgenticX 框架数据模型设计对齐。
搜索结果模型复用 tools.base_search.SearchResultItem。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# 枚举类型
# ============================================================================

class SearchEngine(str, Enum):
    """支持的搜索引擎类型"""
    GOOGLE = "google"
    BING = "bing"
    BOCHAAI = "bochaai"
    MOCK = "mock"


class ResearchPhase(str, Enum):
    """研究阶段枚举"""
    INITIALIZATION = "initialization"
    QUERY_GENERATION = "query_generation"
    SEARCH_EXECUTION = "search_execution"
    RESULT_ANALYSIS = "result_analysis"
    GAP_IDENTIFICATION = "gap_identification"
    REFLECTION = "reflection"
    REPORT_GENERATION = "report_generation"
    QUALITY_ASSESSMENT = "quality_assessment"
    COMPLETED = "completed"


class QueryType(str, Enum):
    """查询类型枚举"""
    INITIAL = "initial"
    FOLLOWUP = "followup"
    CLARIFICATION = "clarification"
    DEEP_DIVE = "deep_dive"


# ============================================================================
# 核心数据模型
# ============================================================================

class SearchQuery(BaseModel):
    """搜索查询数据模型"""
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    query: str = Field(description="搜索查询字符串")
    query_type: QueryType = Field(default=QueryType.INITIAL, description="查询类型")
    language: str = Field(default="zh-CN", description="搜索语言")
    max_results: int = Field(default=10, description="最大结果数")
    search_engines: List[SearchEngine] = Field(
        default_factory=lambda: [SearchEngine.BOCHAAI],
        description="使用的搜索引擎列表"
    )
    freshness: Optional[str] = Field(default=None, description="时效性过滤")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeItem(BaseModel):
    """知识项数据模型"""
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    content: str = Field(description="知识内容")
    type: str = Field(description="知识类型: fact, concept, relationship, timeline, opinion")
    confidence: float = Field(default=5.0, ge=0.0, le=10.0, description="置信度 0-10")
    source: str = Field(default="", description="来源 URL 或标识")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="创建时间"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeGap(BaseModel):
    """知识空白数据模型"""
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    topic: str = Field(description="空白主题")
    description: str = Field(description="空白描述")
    priority: int = Field(default=5, ge=1, le=10, description="优先级 1-10")
    suggested_queries: List[str] = Field(default_factory=list, description="建议的搜索查询")
    identified_by: str = Field(default="", description="识别此空白的智能体")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="识别时间"
    )


class Citation(BaseModel):
    """引用数据模型"""
    source_url: str = Field(description="来源 URL")
    title: str = Field(description="标题")
    author: Optional[str] = Field(default=None, description="作者")
    publication_date: Optional[str] = Field(default=None, description="发布日期")
    access_date: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="访问日期"
    )
    citation_format: str = Field(default="APA", description="引用格式")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def format_citation(self) -> str:
        """格式化引用"""
        if self.citation_format == "APA":
            author_part = f"{self.author}. " if self.author else ""
            date_part = f"({self.publication_date}). " if self.publication_date else ""
            return f"{author_part}{date_part}{self.title}. Retrieved from {self.source_url}"
        return f"{self.title}. {self.source_url}"


# ============================================================================
# 搜索结果模型（兼容层）
# ============================================================================

class SearchResult(BaseModel):
    """搜索结果模型
    
    为 report/interactive 等模块提供向后兼容的搜索结果类型。
    与 tools.base_search.SearchResultItem 字段对齐，但保留独立定义
    以避免循环导入。
    """
    title: str = Field(default="", description="结果标题")
    url: str = Field(default="", description="结果链接")
    snippet: str = Field(default="", description="结果摘要")
    source: SearchEngine = Field(default=SearchEngine.MOCK, description="来源搜索引擎")
    content: str = Field(default="", description="完整内容")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="获取时间"
    )
    relevance_score: Optional[float] = Field(default=None, description="相关性评分")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# 研究过程模型
# ============================================================================

class ResearchIteration(BaseModel):
    """研究迭代数据模型"""
    iteration_id: int = Field(description="迭代编号")
    queries: List[SearchQuery] = Field(default_factory=list, description="本轮查询列表")
    search_results: List[SearchResult] = Field(
        default_factory=list,
        description="搜索结果列表"
    )
    analysis_summary: str = Field(default="", description="分析摘要")
    identified_gaps: List[KnowledgeGap] = Field(default_factory=list, description="识别的知识空白")
    knowledge_items: List[KnowledgeItem] = Field(default_factory=list, description="提取的知识项")
    phase: ResearchPhase = Field(default=ResearchPhase.INITIALIZATION, description="当前阶段")
    start_time: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="开始时间"
    )
    end_time: Optional[str] = Field(default=None, description="结束时间")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResearchContext(BaseModel):
    """研究上下文数据模型（核心状态容器）"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str = Field(default_factory=lambda: str(uuid4()), description="会话 ID")
    research_topic: str = Field(description="研究主题")
    research_objective: str = Field(default="", description="研究目标")
    target_language: str = Field(default="zh-CN", description="目标语言")
    max_iterations: int = Field(default=5, ge=1, le=20, description="最大迭代次数")
    current_iteration: int = Field(default=0, description="当前迭代编号")
    iterations: List[ResearchIteration] = Field(default_factory=list, description="迭代历史")
    overall_findings: str = Field(default="", description="总体发现")
    final_report: str = Field(default="", description="最终报告")
    citations: List[Citation] = Field(default_factory=list, description="引用列表")
    start_time: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="研究开始时间"
    )
    end_time: Optional[str] = Field(default=None, description="研究结束时间")
    status: ResearchPhase = Field(default=ResearchPhase.INITIALIZATION, description="当前状态")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_iteration(self, iteration: ResearchIteration) -> None:
        """添加研究迭代"""
        self.iterations.append(iteration)
        self.current_iteration = len(self.iterations)

    def get_current_iteration(self) -> Optional[ResearchIteration]:
        """获取当前迭代"""
        return self.iterations[-1] if self.iterations else None

    def get_all_search_results(self) -> List[SearchResult]:
        """获取所有搜索结果"""
        all_results: List[SearchResult] = []
        for iteration in self.iterations:
            all_results.extend(iteration.search_results)
        return all_results

    def get_all_knowledge_gaps(self) -> List[KnowledgeGap]:
        """获取所有知识空白"""
        all_gaps = []
        for iteration in self.iterations:
            all_gaps.extend(iteration.identified_gaps)
        return all_gaps

    def should_continue(self) -> bool:
        """判断是否应该继续研究"""
        if self.current_iteration >= self.max_iterations:
            return False
        current_iter = self.get_current_iteration()
        if current_iter and not current_iter.identified_gaps:
            return False
        return True


# ============================================================================
# 报告模型
# ============================================================================

class ReportSection(BaseModel):
    """报告章节数据模型"""
    title: str = Field(description="章节标题")
    content: str = Field(default="", description="章节内容")
    level: int = Field(default=1, ge=1, le=6, description="标题级别")
    citations: List[Citation] = Field(default_factory=list, description="章节引用")
    subsections: List[ReportSection] = Field(default_factory=list, description="子章节")

    def to_markdown(self, base_level: int = 1) -> str:
        """转换为 Markdown 格式"""
        level = min(base_level + self.level - 1, 6)
        header = "#" * level + " " + self.title + "\n\n"
        body = self.content + "\n\n" if self.content else ""

        for subsection in self.subsections:
            body += subsection.to_markdown(base_level + 1)

        return header + body


class ResearchReport(BaseModel):
    """研究报告数据模型"""
    title: str = Field(description="报告标题")
    abstract: str = Field(default="", description="摘要")
    sections: List[ReportSection] = Field(default_factory=list, description="章节列表")
    citations: List[Citation] = Field(default_factory=list, description="参考文献")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="生成时间"
    )

    def to_markdown(self) -> str:
        """转换为完整的 Markdown 报告"""
        report = f"# {self.title}\n\n"
        report += f"## 摘要\n\n{self.abstract}\n\n"

        for section in self.sections:
            report += section.to_markdown(2)

        if self.citations:
            report += "## 参考文献\n\n"
            for i, citation in enumerate(self.citations, 1):
                report += f"{i}. {citation.format_citation()}\n"

        return report
