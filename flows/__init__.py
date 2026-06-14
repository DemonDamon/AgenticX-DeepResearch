"""
AgenticX-DeepResearch 工作流包 (v2)

基于 agenticx.flow 实现的声明式工作流。
"""

from .basic_flow import BasicResearchFlow, ResearchState
from .advanced_flow import AdvancedResearchFlow

__all__ = [
    "BasicResearchFlow",
    "AdvancedResearchFlow",
    "ResearchState",
]
