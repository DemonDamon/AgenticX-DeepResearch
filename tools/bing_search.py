"""
Bing Web Search Tool

基于 BaseSearchTool 统一接口实现的 Bing 搜索引擎工具。
使用 Microsoft Bing Web Search API v7。
"""

import os
import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from .base_search import BaseSearchTool

logger = logging.getLogger(__name__)


class BingWebSearchTool(BaseSearchTool):
    """
    Bing Web Search 工具
    
    使用 Microsoft Bing Web Search API 进行网络搜索。
    支持市场选择、安全搜索级别、时效性过滤。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        market: str = "zh-CN",
        safe_search: str = "Moderate",
        **kwargs
    ):
        super().__init__(
            name="bing_web_search",
            description="使用 Bing 搜索引擎进行网络搜索。输入搜索查询，返回相关网页结果。",
            engine_name="bing",
            timeout=30.0,
            **kwargs
        )
        self.api_key = (
            api_key
            or os.getenv("BING_SUBSCRIPTION_KEY")
            or os.getenv("BING_API_KEY")
            or os.getenv("AZURE_SUBSCRIPTION_KEY", "")
        )
        self.endpoint = endpoint or "https://api.bing.microsoft.com/v7.0/search"
        self.market = market
        self.safe_search = safe_search

        if not self.api_key:
            logger.warning("[Bing] 未配置 API Key (BING_SUBSCRIPTION_KEY / BING_API_KEY)")

    def _execute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """执行 Bing 搜索请求"""
        if not self.api_key:
            logger.error("[Bing] API Key 未配置，无法执行搜索")
            return []

        params: Dict[str, Any] = {
            "q": query,
            "count": min(max(max_results, 1), 50),
            "offset": 0,
            "mkt": language or self.market,
            "safesearch": self.safe_search,
        }

        # 时效性过滤
        if freshness:
            freshness_map = {"day": "Day", "week": "Week", "month": "Month"}
            bing_freshness = freshness_map.get(freshness.lower())
            if bing_freshness:
                params["freshness"] = bing_freshness

        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(url)
            req.add_header("Ocp-Apim-Subscription-Key", self.api_key)
            req.add_header("User-Agent", "AgenticX-DeepResearch/2.0")

            with urllib.request.urlopen(req, timeout=30) as response:
                raw_data = response.read().decode("utf-8")
                data = json.loads(raw_data)

            results = []
            if "webPages" in data and "value" in data["webPages"]:
                for item in data["webPages"]["value"]:
                    results.append({
                        "title": item.get("name", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                        "display_url": item.get("displayUrl"),
                        "date_crawled": item.get("dateLastCrawled"),
                    })

            logger.info(f"[Bing] 搜索 '{query}' 返回 {len(results)} 条结果")
            return results

        except urllib.error.HTTPError as e:
            error_msg = f"Bing API HTTP 错误: {e.code} - {e.reason}"
            if e.code == 401:
                error_msg += " (请检查 BING_SUBSCRIPTION_KEY)"
            elif e.code == 429:
                error_msg += " (请求过于频繁)"
            logger.error(error_msg)
            return []

        except urllib.error.URLError as e:
            logger.error(f"[Bing] 网络连接错误: {e.reason}")
            return []

        except json.JSONDecodeError as e:
            logger.error(f"[Bing] JSON 解析错误: {e}")
            return []

        except Exception as e:
            logger.error(f"[Bing] 搜索异常: {e}")
            return []

    async def _aexecute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """异步执行 Bing 搜索请求"""
        try:
            import aiohttp
        except ImportError:
            import asyncio
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._execute_search(query, max_results, language, freshness)
            )

        if not self.api_key:
            return []

        params = {
            "q": query,
            "count": str(min(max(max_results, 1), 50)),
            "mkt": language or self.market,
            "safesearch": self.safe_search,
        }

        if freshness:
            freshness_map = {"day": "Day", "week": "Week", "month": "Month"}
            bing_freshness = freshness_map.get(freshness.lower())
            if bing_freshness:
                params["freshness"] = bing_freshness

        headers = {"Ocp-Apim-Subscription-Key": self.api_key}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.endpoint,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30.0)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

            results = []
            if "webPages" in data and "value" in data["webPages"]:
                for item in data["webPages"]["value"]:
                    results.append({
                        "title": item.get("name", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                        "display_url": item.get("displayUrl"),
                        "date_crawled": item.get("dateLastCrawled"),
                    })

            return results

        except Exception as e:
            logger.error(f"[Bing] 异步搜索异常: {e}")
            return []


# ============================================================================
# Mock 工具（测试用）
# ============================================================================

class MockBingSearchTool(BaseSearchTool):
    """Bing 模拟搜索工具（用于测试和开发）"""

    def __init__(self, **kwargs):
        super().__init__(
            name="mock_bing_web_search",
            description="模拟 Bing 搜索工具（测试用）",
            engine_name="bing_mock",
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
            ("深度分析报告", "analysis"),
            ("最新发展动态", "news"),
            ("未来展望与挑战", "outlook"),
            ("核心技术解读", "tech"),
            ("行业应用案例", "case"),
        ]

        for i, (label, category) in enumerate(templates[:max_results]):
            mock_results.append({
                "title": f"[MockBing] {query} - {label}",
                "url": f"https://example.com/bing/{category}/{query.replace(' ', '-')}-{i+1}",
                "snippet": f"Bing 模拟结果: 关于 '{query}' 的{label}，涵盖多个重要维度的分析。",
                "display_url": f"example.com/bing/{category}/...",
                "date_crawled": "2025-01-01T00:00:00Z",
            })

        logger.info(f"[MockBing] 模拟搜索 '{query}' 返回 {len(mock_results)} 条结果")
        return mock_results
