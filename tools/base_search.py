"""
BaseSearchTool: 深度搜索系统的统一搜索工具基类

所有搜索引擎工具继承此基类，确保输出格式统一。
基于 agenticx.tools.base.BaseTool 实现。
"""

import logging
from abc import abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field

from agenticx.tools.base import BaseTool

logger = logging.getLogger(__name__)


class SearchInput(BaseModel):
    """统一的搜索输入模型"""
    query: str = Field(description="搜索查询字符串")
    max_results: int = Field(default=10, description="最大返回结果数")
    language: str = Field(default="zh-CN", description="搜索语言")
    freshness: Optional[str] = Field(default=None, description="时效性过滤: day/week/month/year")
    fetch_content: bool = Field(default=False, description="是否抓取搜索结果全文")
    content_max_chars: int = Field(default=12000, description="单篇全文最大字符数")


class SearchResultItem(BaseModel):
    """统一的搜索结果条目模型
    
    所有搜索引擎返回的结果都会被标准化为此格式。
    """
    title: str = Field(description="结果标题")
    url: str = Field(description="结果链接 URL")
    snippet: str = Field(description="结果摘要/片段")
    source: str = Field(default="unknown", description="来源搜索引擎标识")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="结果获取时间"
    )
    relevance_score: Optional[float] = Field(default=None, description="相关性评分")
    content: Optional[str] = Field(default=None, description="完整网页内容（如有抓取）")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="额外元数据")

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return self.model_dump()


class SearchResponse(BaseModel):
    """统一的搜索响应模型"""
    query: str = Field(description="原始查询")
    results: List[SearchResultItem] = Field(default_factory=list, description="搜索结果列表")
    total_results: int = Field(default=0, description="总结果数")
    search_engine: str = Field(default="unknown", description="搜索引擎名称")
    execution_time: Optional[float] = Field(default=None, description="执行耗时（秒）")
    error: Optional[str] = Field(default=None, description="错误信息")


class BaseSearchTool(BaseTool):
    """
    深度搜索系统的统一搜索工具基类
    
    所有搜索引擎工具（BochaaI, Bing, Google）都继承此基类。
    确保：
    1. 统一的输入参数格式 (SearchInput)
    2. 统一的输出格式 (SearchResponse)
    3. 标准的错误处理和重试逻辑
    4. 统一的回调和可观测性接口
    """

    def __init__(
        self,
        name: str,
        description: str,
        engine_name: str = "unknown",
        timeout: Optional[float] = 30.0,
        max_retries: int = 3,
        **kwargs
    ):
        super().__init__(
            name=name,
            description=description,
            args_schema=SearchInput,
            timeout=timeout,
            **kwargs
        )
        self.engine_name = engine_name
        self.max_retries = max_retries

    def _run(self, **kwargs) -> Dict[str, Any]:
        """
        同步执行搜索
        
        子类应实现 _execute_search 方法。
        """
        import time
        start_time = time.time()

        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 10)
        language = kwargs.get("language", "zh-CN")
        freshness = kwargs.get("freshness")
        fetch_content = kwargs.get("fetch_content", False)
        content_max_chars = kwargs.get("content_max_chars", 12000)

        try:
            raw_results = self._execute_search(
                query=query,
                max_results=max_results,
                language=language,
                freshness=freshness
            )
            
            # 标准化结果
            standardized = self._standardize_results(raw_results, query)
            if fetch_content:
                standardized = self._fetch_content_sync(standardized, content_max_chars)
            execution_time = time.time() - start_time

            response = SearchResponse(
                query=query,
                results=standardized,
                total_results=len(standardized),
                search_engine=self.engine_name,
                execution_time=execution_time
            )
            return response.model_dump()

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[{self.engine_name}] 搜索失败: {e}")
            response = SearchResponse(
                query=query,
                results=[],
                total_results=0,
                search_engine=self.engine_name,
                execution_time=execution_time,
                error=str(e)
            )
            return response.model_dump()

    async def _arun(self, **kwargs) -> Dict[str, Any]:
        """
        异步执行搜索
        
        子类可重写 _aexecute_search 方法提供真正的异步实现。
        """
        import time
        start_time = time.time()

        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 10)
        language = kwargs.get("language", "zh-CN")
        freshness = kwargs.get("freshness")
        fetch_content = kwargs.get("fetch_content", False)
        content_max_chars = kwargs.get("content_max_chars", 12000)

        try:
            raw_results = await self._aexecute_search(
                query=query,
                max_results=max_results,
                language=language,
                freshness=freshness
            )
            
            standardized = self._standardize_results(raw_results, query)
            if fetch_content:
                standardized = await self._fetch_content_async(standardized, content_max_chars)
            execution_time = time.time() - start_time

            response = SearchResponse(
                query=query,
                results=standardized,
                total_results=len(standardized),
                search_engine=self.engine_name,
                execution_time=execution_time
            )
            return response.model_dump()

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[{self.engine_name}] 异步搜索失败: {e}")
            response = SearchResponse(
                query=query,
                results=[],
                total_results=0,
                search_engine=self.engine_name,
                execution_time=execution_time,
                error=str(e)
            )
            return response.model_dump()

    @abstractmethod
    def _execute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        执行实际的搜索请求（子类必须实现）
        
        Args:
            query: 搜索查询
            max_results: 最大结果数
            language: 语言
            freshness: 时效性过滤
            
        Returns:
            原始搜索结果列表（字典格式）
        """
        pass

    async def _aexecute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        异步执行搜索请求（默认回退到同步实现）
        
        子类可重写此方法提供真正的异步实现。
        """
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._execute_search(query, max_results, language, freshness)
        )

    def _standardize_results(
        self,
        raw_results: List[Dict[str, Any]],
        query: str
    ) -> List[SearchResultItem]:
        """
        将原始搜索结果标准化为 SearchResultItem 列表
        
        子类可重写此方法自定义标准化逻辑。
        """
        standardized = []
        for item in raw_results:
            try:
                result = SearchResultItem(
                    title=item.get("title", ""),
                    url=item.get("url") or item.get("link", ""),
                    snippet=item.get("snippet") or item.get("description", ""),
                    source=self.engine_name,
                    relevance_score=item.get("relevance_score"),
                    content=item.get("content"),
                    metadata={
                        k: v for k, v in item.items()
                        if k not in ("title", "url", "link", "snippet", "description",
                                     "relevance_score", "content")
                    }
                )
                standardized.append(result)
            except Exception as e:
                logger.warning(f"[{self.engine_name}] 结果标准化失败: {e}")
                continue
        return standardized

    async def _fetch_content_async(
        self,
        results: List[SearchResultItem],
        max_chars: int,
    ) -> List[SearchResultItem]:
        """Enrich search results with full Markdown content when possible."""
        import asyncio
        from tools.content_fetch import JinaContentFetcher

        fetcher = JinaContentFetcher(max_chars=max_chars)

        async def enrich(item: SearchResultItem) -> SearchResultItem:
            if not item.url or item.content:
                return item
            fetched = await fetcher.fetch(item.url)
            if fetched.ok and fetched.content:
                item.content = fetched.content
                item.metadata["content_fetcher"] = "jina"
                item.metadata["content_status_code"] = fetched.status_code
            elif fetched.error:
                item.metadata["content_fetch_error"] = fetched.error
            return item

        return await asyncio.gather(*(enrich(item) for item in results))

    def _fetch_content_sync(
        self,
        results: List[SearchResultItem],
        max_chars: int,
    ) -> List[SearchResultItem]:
        """Synchronous wrapper for content enrichment."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._fetch_content_async(results, max_chars))

        if loop.is_running():
            logger.warning("Skipping sync content fetch inside a running event loop")
            return results
        return loop.run_until_complete(self._fetch_content_async(results, max_chars))
