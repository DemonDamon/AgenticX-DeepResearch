"""Full-content fetching utilities for deep research.

P0 uses a Jina Reader compatible URL prefix because it is easy to mock in tests
and provides LLM-ready Markdown without introducing browser infrastructure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ContentFetchResult:
    url: str
    content: str = ""
    ok: bool = False
    status_code: Optional[int] = None
    error: Optional[str] = None


class JinaContentFetcher:
    """Fetch Markdown page content through a Jina Reader compatible endpoint."""

    def __init__(
        self,
        reader_base_url: str = "https://r.jina.ai/",
        timeout: float = 20.0,
        max_chars: int = 12000,
    ) -> None:
        self.reader_base_url = reader_base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.max_chars = max_chars

    async def fetch(self, url: str) -> ContentFetchResult:
        reader_url = self.build_reader_url(url)
        try:
            response = await self._client_get(reader_url, timeout=self.timeout)
            response.raise_for_status()
            content = (response.text or "").strip()
            if self.max_chars and len(content) > self.max_chars:
                content = content[: self.max_chars].rsplit("\n", 1)[0].strip()
            return ContentFetchResult(
                url=url,
                content=content,
                ok=True,
                status_code=response.status_code,
            )
        except Exception as exc:
            logger.warning("Content fetch failed for %s: %s", url, exc)
            return ContentFetchResult(url=url, ok=False, error=str(exc))

    def build_reader_url(self, url: str) -> str:
        # Jina supports raw URL after the prefix. Quote only whitespace/control
        # characters to preserve the familiar r.jina.ai/http://... form.
        safe_url = quote(url.strip(), safe=":/?#[]@!$&'()*+,;=%")
        return f"{self.reader_base_url}{safe_url}"

    async def _client_get(self, url: str, **kwargs):
        async with httpx.AsyncClient(follow_redirects=True) as client:
            return await client.get(url, **kwargs)
