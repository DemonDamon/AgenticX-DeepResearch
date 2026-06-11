"""
Google Web Search Tool

基于 BaseSearchTool 统一接口实现的 Google 搜索引擎工具。
支持 Google Custom Search JSON API 和 Google GenAI 搜索。
"""

import os
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional

from .base_search import BaseSearchTool

logger = logging.getLogger(__name__)


class GoogleSearchTool(BaseSearchTool):
    """
    Google 搜索工具
    
    支持两种模式：
    1. Google Custom Search JSON API (需要 GOOGLE_API_KEY + GOOGLE_CX_ID)
    2. Google GenAI 搜索 (需要 GOOGLE_API_KEY，使用 Gemini grounding)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cx_id: Optional[str] = None,
        use_genai: bool = False,
        **kwargs
    ):
        super().__init__(
            name="google_web_search",
            description="使用 Google 搜索引擎进行网络搜索。输入搜索查询，返回相关网页结果。",
            engine_name="google",
            timeout=30.0,
            **kwargs
        )
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        self.cx_id = cx_id or os.getenv("GOOGLE_CX_ID", "")
        self.use_genai = use_genai
        self.endpoint = "https://www.googleapis.com/customsearch/v1"

        if not self.api_key:
            logger.warning("[Google] 未配置 API Key (GOOGLE_API_KEY / GEMINI_API_KEY)")

    def _execute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """执行 Google 搜索请求"""
        if self.use_genai:
            return self._execute_genai_search(query, max_results)
        return self._execute_custom_search(query, max_results, language, freshness)

    def _execute_custom_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """使用 Google Custom Search JSON API"""
        if not self.api_key or not self.cx_id:
            logger.error("[Google] API Key 或 CX ID 未配置")
            return []

        params = {
            "key": self.api_key,
            "cx": self.cx_id,
            "q": query,
            "num": min(max(max_results, 1), 10),  # Google CSE 最多 10 条/请求
            "lr": f"lang_{language[:2]}",
        }

        # 时效性过滤
        if freshness:
            date_restrict_map = {
                "day": "d1",
                "week": "w1",
                "month": "m1",
                "year": "y1",
            }
            date_restrict = date_restrict_map.get(freshness.lower())
            if date_restrict:
                params["dateRestrict"] = date_restrict

        url = f"{self.endpoint}?{urllib.parse.urlencode(params)}"

        try:
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "AgenticX-DeepResearch/2.0")

            with urllib.request.urlopen(req, timeout=30) as response:
                raw_data = response.read().decode("utf-8")
                data = json.loads(raw_data)

            results = []
            for item in data.get("items", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "display_url": item.get("displayLink"),
                })

            logger.info(f"[Google] 搜索 '{query}' 返回 {len(results)} 条结果")
            return results

        except urllib.error.HTTPError as e:
            logger.error(f"[Google] HTTP 错误: {e.code} - {e.reason}")
            return []

        except Exception as e:
            logger.error(f"[Google] 搜索异常: {e}")
            return []

    def _execute_genai_search(
        self,
        query: str,
        max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """使用 Google GenAI 搜索 (Gemini grounding)"""
        try:
            from google import genai

            client = genai.Client(api_key=self.api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=f"Search the web for: {query}",
                config={
                    "tools": [{"google_search": {}}],
                }
            )

            results = []
            if hasattr(response, "candidates") and response.candidates:
                for candidate in response.candidates:
                    if hasattr(candidate, "grounding_metadata"):
                        metadata = candidate.grounding_metadata
                        if hasattr(metadata, "grounding_chunks"):
                            for chunk in metadata.grounding_chunks[:max_results]:
                                if hasattr(chunk, "web"):
                                    results.append({
                                        "title": getattr(chunk.web, "title", "") or "",
                                        "url": getattr(chunk.web, "uri", "") or "",
                                        "snippet": "",
                                    })

            logger.info(f"[Google GenAI] 搜索 '{query}' 返回 {len(results)} 条结果")
            return results

        except ImportError:
            logger.error("[Google] google-genai 未安装，请执行: pip install google-genai")
            return []
        except Exception as e:
            logger.error(f"[Google GenAI] 搜索异常: {e}")
            return []

    async def _aexecute_search(
        self,
        query: str,
        max_results: int = 10,
        language: str = "zh-CN",
        freshness: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """异步执行 Google 搜索（回退到同步）"""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._execute_search(query, max_results, language, freshness)
        )


# ============================================================================
# Mock 工具（测试用）
# ============================================================================

class MockGoogleSearchTool(BaseSearchTool):
    """Google 模拟搜索工具（用于测试和开发）"""

    def __init__(self, **kwargs):
        super().__init__(
            name="mock_google_web_search",
            description="模拟 Google 搜索工具（测试用）",
            engine_name="google_mock",
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
            ("权威解读", "authority"),
            ("学术论文", "paper"),
            ("官方文档", "docs"),
            ("社区讨论", "community"),
            ("视频教程", "tutorial"),
        ]

        for i, (label, category) in enumerate(templates[:max_results]):
            mock_results.append({
                "title": f"[MockGoogle] {query} - {label}",
                "url": f"https://example.com/google/{category}/{query.replace(' ', '-')}-{i+1}",
                "snippet": f"Google 模拟结果: 关于 '{query}' 的{label}内容，提供深入的分析视角。",
                "display_url": f"example.com/google/{category}/...",
            })

        logger.info(f"[MockGoogle] 模拟搜索 '{query}' 返回 {len(mock_results)} 条结果")
        return mock_results
