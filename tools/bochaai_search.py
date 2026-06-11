"""
BochaaI Web Search Tool

基于 BaseSearchTool 统一接口实现的博查AI搜索引擎工具。
支持中文优化搜索、时效性过滤、AI摘要生成等高级功能。
"""

import os
import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base_search import BaseSearchTool, SearchResultItem

logger = logging.getLogger(__name__)


# ============================================================================
# BochaaI 搜索工具
# ============================================================================

class BochaaIWebSearchTool(BaseSearchTool):
    """
    博查AI (BochaaI) 搜索工具
    
    特性：
    - 中文搜索优化
    - 支持时效性过滤 (freshness)
    - 支持 AI 摘要生成
    - 支持域名包含/排除过滤
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        enable_summary: bool = False,
        include: Optional[str] = None,
        exclude: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            name="bochaai_web_search",
            description="使用博查AI搜索引擎进行网络搜索，支持中文优化和AI摘要。输入搜索查询，返回相关网页结果。",
            engine_name="bochaai",
            timeout=30.0,
            **kwargs
        )
        self.api_key = api_key or os.getenv("BOCHAAI_API_KEY", "")
        self.endpoint = endpoint or "https://api.bochaai.com/v1/web-search"
        self.enable_summary = enable_summary
        self.include = include
        self.exclude = exclude

        if not self.api_key:
            logger.warning("[BochaaI] 未配置 API Key (BOCHAAI_API_KEY)")

    def _execute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """执行 BochaaI 搜索请求"""
        if not self.api_key:
            logger.error("[BochaaI] API Key 未配置，无法执行搜索")
            return []

        # 构建请求数据
        request_data: Dict[str, Any] = {
            "query": query,
            "count": min(max(max_results, 1), 50),
            "freshness": freshness or "noLimit",
            "summary": self.enable_summary,
        }

        if self.include:
            request_data["include"] = self.include
        if self.exclude:
            request_data["exclude"] = self.exclude

        try:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(request_data).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AgenticX-DeepResearch/2.0"
                }
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                raw_data = response.read().decode("utf-8")
                result = json.loads(raw_data)

            # 解析 BochaaI 响应结构: {"code": 200, "data": {"webPages": {"value": [...]}}}
            results = []
            data = result.get("data", {})

            if "webPages" in data and data["webPages"]:
                for item in data["webPages"].get("value", []):
                    results.append({
                        "title": item.get("name", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                        "summary": item.get("summary"),
                        "site_name": item.get("siteName"),
                        "date_published": item.get("datePublished"),
                        "date_crawled": item.get("dateLastCrawled"),
                        "language": item.get("language"),
                    })

            logger.info(f"[BochaaI] 搜索 '{query}' 返回 {len(results)} 条结果")
            return results

        except urllib.error.HTTPError as e:
            error_msg = f"BochaaI API HTTP 错误: {e.code} - {e.reason}"
            if e.code == 401:
                error_msg += " (请检查 BOCHAAI_API_KEY)"
            elif e.code == 429:
                error_msg += " (请求过于频繁)"
            logger.error(error_msg)
            return []

        except urllib.error.URLError as e:
            logger.error(f"[BochaaI] 网络连接错误: {e.reason}")
            return []

        except json.JSONDecodeError as e:
            logger.error(f"[BochaaI] JSON 解析错误: {e}")
            return []

        except Exception as e:
            logger.error(f"[BochaaI] 搜索异常: {e}")
            return []

    async def _aexecute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """异步执行 BochaaI 搜索请求"""
        try:
            import aiohttp
        except ImportError:
            # 回退到同步实现
            import asyncio
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._execute_search(query, max_results, language, freshness)
            )

        if not self.api_key:
            return []

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "query": query,
            "count": min(max(max_results, 1), 50),
            "freshness": freshness or "noLimit",
            "summary": self.enable_summary,
        }

        if self.include:
            payload["include"] = self.include
        if self.exclude:
            payload["exclude"] = self.exclude

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30.0)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            results = []
            api_data = data.get("data", {})
            if "webPages" in api_data and api_data["webPages"]:
                for item in api_data["webPages"].get("value", []):
                    results.append({
                        "title": item.get("name", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                        "summary": item.get("summary"),
                        "site_name": item.get("siteName"),
                        "date_published": item.get("datePublished"),
                        "date_crawled": item.get("dateLastCrawled"),
                    })

            return results

        except Exception as e:
            logger.error(f"[BochaaI] 异步搜索异常: {e}")
            return []


# ============================================================================
# Mock 工具（测试用）
# ============================================================================

class MockBochaaISearchTool(BaseSearchTool):
    """BochaaI 模拟搜索工具（用于测试和开发）"""

    def __init__(self, **kwargs):
        super().__init__(
            name="mock_bochaai_web_search",
            description="模拟博查AI搜索工具（测试用）",
            engine_name="bochaai_mock",
            timeout=5.0,
            **kwargs
        )

    def _execute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """返回模拟搜索结果"""
        mock_results = []
        templates = [
            ("深度分析", "research"),
            ("最新进展", "news"),
            ("技术解析", "tech"),
            ("行业报告", "report"),
            ("专家观点", "expert"),
        ]

        for i, (label, category) in enumerate(templates[:max_results]):
            mock_results.append({
                "title": f"[Mock] {query} - {label}",
                "url": f"https://example.com/{category}/{query.replace(' ', '-')}-{i+1}",
                "snippet": f"这是关于 '{query}' 的模拟搜索结果（{label}）。包含详细的分析和数据支持。",
                "summary": f"AI摘要: {query} 是一个重要的研究方向，本文从{label}角度进行了深入探讨。",
                "site_name": f"Mock {label} Site",
                "date_published": "2025-01-01T00:00:00Z",
            })

        logger.info(f"[MockBochaaI] 模拟搜索 '{query}' 返回 {len(mock_results)} 条结果")
        return mock_results
