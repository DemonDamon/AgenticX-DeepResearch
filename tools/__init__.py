"""
AgenticX-DeepResearch 工具包

提供统一的搜索引擎工具接口，所有工具继承自 BaseSearchTool（基于 agenticx.tools.base.BaseTool）。
统一的输入输出格式确保搜索引擎可以无缝切换。
"""

# 统一基类和数据模型
from pydantic import BaseModel

from .base_search import BaseSearchTool, SearchInput, SearchResultItem, SearchResponse


class SearchResult(BaseModel):
    title: str = ""
    link: str = ""
    snippet: str = ""

# BochaaI 搜索引擎
from .bochaai_search import BochaaIWebSearchTool, MockBochaaISearchTool

# Bing 搜索引擎
from .bing_search import BingWebSearchTool, MockBingSearchTool

# Google 搜索引擎
from .google_search import GoogleSearchTool, MockGoogleSearchTool

# 多模态工具
from .multimodal_doc import MultimodalDocTool
from .content_fetch import ContentFetchResult, JinaContentFetcher

# Backward-compatible aliases used by main.py and older docs.
BochaaISearchTool = BochaaIWebSearchTool
BingSearchTool = BingWebSearchTool

__all__ = [
    # 基础抽象和数据模型
    "BaseSearchTool",
    "SearchInput",
    "SearchResultItem",
    "SearchResult",
    "SearchResponse",
    # BochaaI
    "BochaaIWebSearchTool",
    "BochaaISearchTool",
    "MockBochaaISearchTool",
    # Bing
    "BingWebSearchTool",
    "BingSearchTool",
    "MockBingSearchTool",
    # Google
    "GoogleSearchTool",
    "MockGoogleSearchTool",
    # Multimodal
    "MultimodalDocTool",
    # Content fetching
    "ContentFetchResult",
    "JinaContentFetcher",
]
