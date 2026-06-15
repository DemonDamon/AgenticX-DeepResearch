import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class NearAgentMessage(BaseModel):
    """Near AI Agent 消息格式 (参考 A2A 标准)"""
    message_id: str
    sender: str
    receiver: str
    content: Dict[str, Any]
    attestation: Optional[str] = None # TEE 证明 (Near 特色)

class NearAdapter:
    """
    Near AI 协议适配层
    负责将 AgenticX-DeepResearch 挂载到 Near AI 生态
    """
    def __init__(self, agent_id: str, near_account: str):
        self.agent_id = agent_id
        self.near_account = near_account
        self.is_connected = False

    async def connect(self):
        """连接到 Near AI Agent Registry/Marketplace"""
        logger.info(f"Connecting Agent {self.agent_id} to Near AI as {self.near_account}...")
        # 模拟连接逻辑
        await asyncio.sleep(1)
        self.is_connected = True
        logger.info("Successfully connected to Near AI.")

    async def handle_request(self, message: NearAgentMessage) -> Dict[str, Any]:
        """
        处理来自 Near 网络的请求
        将 Near 消息转换为内部 ResearchRequest
        """
        topic = message.content.get("topic")
        objective = message.content.get("objective")
        mode = message.content.get("mode", "basic")
        
        logger.info(f"Received Near AI research request: {topic}")
        
        # 这里后续将调用 FastAPI 内部逻辑或直接触发 Flow
        return {
            "status": "accepted",
            "task_id": "near_" + message.message_id,
            "info": f"Research on '{topic}' started via Near AI Adapter."
        }

    def get_agent_card(self) -> Dict[str, Any]:
        """
        生成 Near Agent Card (元数据)
        用于在 Marketplace 展示
        """
        return {
            "name": "AgenticX Deep Research",
            "version": "1.0.0",
            "description": "基于 AgenticX 的深度调研智能体，支持多脑协同与 GraphRAG。",
            "capabilities": ["deep_research", "market_analysis", "tech_scouting"],
            "endpoints": {
                "research": "/api/research/task"
            },
            "near_account": self.near_account,
            "fee_structure": {
                "per_research": "0.1 NEAR"
            }
        }

# 单例适配器
near_adapter = NearAdapter(
    agent_id="agenticx-deep-research-v1",
    near_account=os.getenv("NEAR_ACCOUNT", "agenticx.near")
)
