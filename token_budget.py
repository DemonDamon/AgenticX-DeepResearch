"""Token budget helpers for context-safe truncation.

The project should avoid raw character slicing for LLM context control.  This
module prefers tiktoken when available and falls back to a conservative local
estimate so tests and offline deployments keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TokenBudget:
    """Count and truncate text by token budget."""

    model_name: str = "gpt-4o-mini"
    max_tokens: int = 4000

    def __post_init__(self) -> None:
        self._encoding = self._load_encoding(self.model_name)

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return len(self._fallback_encode(text))

    def truncate(self, text: str, max_tokens: Optional[int] = None) -> str:
        """Return text truncated to a token budget."""
        if not text:
            return ""

        budget = max_tokens or self.max_tokens
        if budget <= 0:
            return ""

        if self._encoding is not None:
            tokens = self._encoding.encode(text)
            if len(tokens) <= budget:
                return text
            return self._encoding.decode(tokens[:budget]).strip()

        tokens = self._fallback_encode(text)
        if len(tokens) <= budget:
            return text
        return "".join(tokens[:budget]).strip()

    @staticmethod
    def _load_encoding(model_name: str):
        try:
            import tiktoken

            try:
                return tiktoken.encoding_for_model(model_name)
            except KeyError:
                return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None

    @staticmethod
    def _fallback_encode(text: str) -> List[str]:
        # Conservative mixed-language approximation: CJK chars count as tokens,
        # while contiguous latin/number spans are grouped roughly by 4 chars.
        tokens: List[str] = []
        latin_buffer = ""
        for char in text:
            if "\u4e00" <= char <= "\u9fff":
                if latin_buffer:
                    tokens.extend(
                        latin_buffer[i : i + 4]
                        for i in range(0, len(latin_buffer), 4)
                    )
                    latin_buffer = ""
                tokens.append(char)
            elif char.isspace():
                if latin_buffer:
                    tokens.extend(
                        latin_buffer[i : i + 4]
                        for i in range(0, len(latin_buffer), 4)
                    )
                    latin_buffer = ""
            else:
                latin_buffer += char
        if latin_buffer:
            tokens.extend(latin_buffer[i : i + 4] for i in range(0, len(latin_buffer), 4))
        return tokens
