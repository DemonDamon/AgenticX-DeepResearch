"""
AgenticX-DeepResearch 工具包

提供统一的搜索引擎工具接口，所有工具继承自 BaseSearchTool（基于 agenticx.tools.base.BaseTool）。
统一的输入输出格式确保搜索引擎可以无缝切换。
"""

# 统一基类和数据模型
from .base_search import BaseSearchTool, SearchInput, SearchResultItem, SearchResponse

# BochaaI 搜索引擎
from .bochaai_search import BochaaIWebSearchTool, MockBochaaISearchTool

# Bing 搜索引擎
from .bing_search import BingWebSearchTool, MockBingSearchTool

# Google 搜索引擎
from .google_search import GoogleSearchTool, MockGoogleSearchTool

__all__ = [
    # 基础抽象和数据模型
    "BaseSearchTool",
    "SearchInput",
    "SearchResultItem",
    "SearchResponse",
    # BochaaI
    "BochaaIWebSearchTool",
    "MockBochaaISearchTool",
    # Bing
    "BingWebSearchTool",
    "MockBingSearchTool",
    # Google
    "GoogleSearchTool",
    "MockGoogleSearchTool",
]
