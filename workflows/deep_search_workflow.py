"""Compatibility wrapper for the original DeepSearchWorkflow API.

The current project uses `UnifiedResearchWorkflow` and the v2 flow package, but
older tests and examples still import `workflows.deep_search_workflow`.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from tools import MockGoogleSearchTool
from utils import load_config


class DeepSearchWorkflow:
    """Small synchronous compatibility workflow used by legacy tests."""

    def __init__(
        self,
        llm_provider: Optional[Any] = None,
        max_research_loops: int = 3,
        search_engine: str = "mock",
        config_path: str = "config.yaml",
        organization_id: str = "deepsearch",
        **kwargs,
    ) -> None:
        self.llm_provider = llm_provider
        self.max_research_loops = max_research_loops
        self.search_engine = search_engine
        self.organization_id = organization_id
        self.config = load_config(config_path)
        self.search_tool = MockGoogleSearchTool()
        self.reset_metrics()

    def reset_metrics(self) -> None:
        self.metrics = {
            "execution_time": 0.0,
            "search_count": 0,
            "loop_count": 0,
            "error_count": 0,
            "success_rate": 0.0,
        }

    def get_metrics(self) -> Dict[str, Any]:
        return dict(self.metrics)

    def execute(self, research_topic: str) -> Dict[str, Any]:
        start = time.time()
        findings = []
        queries = self._generate_queries(research_topic)

        for loop_idx in range(self.max_research_loops):
            self.metrics["loop_count"] = loop_idx + 1
            for query in queries:
                try:
                    results = self.search_tool._run(query)
                    self.metrics["search_count"] += 1
                    findings.extend(item.get("snippet", "") for item in results)
                except Exception:
                    self.metrics["error_count"] += 1
            break

        final_report = self._generate_report(research_topic, findings)
        self.metrics["execution_time"] = time.time() - start
        attempts = self.metrics["search_count"] + self.metrics["error_count"]
        self.metrics["success_rate"] = self.metrics["search_count"] / attempts if attempts else 0.0

        return {
            "success": True,
            "research_topic": research_topic,
            "final_report": final_report,
            "research_context": {"findings": findings, "queries": queries},
            "total_loops": self.metrics["loop_count"],
            "metrics": self.get_metrics(),
        }

    def _generate_queries(self, topic: str):
        if self.llm_provider and hasattr(self.llm_provider, "invoke"):
            try:
                response = self.llm_provider.invoke(f"Generate search queries for {topic}")
                content = getattr(response, "content", "")
                if "queries" in content:
                    import json

                    parsed = json.loads(content)
                    return parsed.get("queries", []) or [topic]
            except Exception:
                self.metrics["error_count"] += 1
        return [f"{topic} 最新研究", f"{topic} 详细分析"]

    def _generate_report(self, topic: str, findings) -> str:
        if self.llm_provider and hasattr(self.llm_provider, "invoke"):
            try:
                response = self.llm_provider.invoke(f"Write report for {topic}")
                content = getattr(response, "content", "")
                if content:
                    return content
            except Exception:
                self.metrics["error_count"] += 1
        body = "\n".join(f"- {finding}" for finding in findings[:10])
        return f"# {topic}\n\n{body or '暂无发现'}"
