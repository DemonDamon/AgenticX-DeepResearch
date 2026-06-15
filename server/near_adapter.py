"""
Near AI / A2A / MCP 协议适配层 (v2)

实现三层协议适配：
1. Google A2A (Agent-to-Agent) 协议 - 开放标准，支持 Agent 发现和任务委托
2. MCP (Model Context Protocol) Server - 兼容 IronClaw/NEAR AI Cloud 原生接入
3. Near AI Cloud Webhook - 基于 HTTP 回调的 Near 平台集成

架构说明：
- NEAR AI Cloud (IronClaw) 通过 MCP 协议调用本 Agent 的 deep_research Tool
- 任何支持 A2A 协议的 Agent（如 Claude、Gemini）可通过 /.well-known/agent.json 发现并委托任务
- 旧版 nearai Python SDK 已于 2025-10-31 关闭，本实现不依赖该 SDK

参考规范：
- A2A Protocol: https://google.github.io/A2A/
- MCP Specification: https://spec.modelcontextprotocol.io/
- NEAR AI Cloud: https://cloud.near.ai (IronClaw framework)
"""

import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/protocols", tags=["A2A / MCP / Near"])


# ═══════════════════════════════════════════════════════════════════
# 1. A2A 协议 - Agent Card & Task Delegation
# ═══════════════════════════════════════════════════════════════════

AGENT_CARD = {
    "schema_version": "0.2.5",
    "name": "AgenticX Deep Research Agent",
    "description": (
        "一个基于 AgenticX 框架构建的深度调研智能体。"
        "能够对任意主题进行多轮迭代搜索、自适应规划和深度报告生成。"
        "支持多模态输入（文本、PDF、图片），具备长程记忆和知识图谱沉淀能力。"
    ),
    "version": "0.5.0",
    "url": "https://your-deployment-domain.com",
    "capabilities": {
        "streaming": True,
        "push_notifications": True,
        "state_transition_history": True,
        "multi_modal_input": True,
    },
    "authentication": {"schemes": ["bearer"]},
    "skills": [
        {
            "id": "deep_research",
            "name": "深度调研",
            "description": "对指定主题进行多轮迭代深度调研，生成结构化研究报告。",
            "tags": ["research", "analysis", "report"],
            "examples": [
                "调研 2025 年大模型推理优化的最新进展",
                "分析 NEAR 协议的生态发展现状",
                "对比 ReAct、CoT 和 Tree-of-Thought 三种推理范式"
            ],
            "input_modes": ["text", "file"],
            "output_modes": ["text", "file"],
        },
        {
            "id": "knowledge_graph_export",
            "name": "知识图谱导出",
            "description": "将调研结果导出为结构化知识图谱（GraphRAG 格式）。",
            "tags": ["knowledge", "graph", "export"],
            "input_modes": ["text"],
            "output_modes": ["data"],
        }
    ],
    "provider": {
        "organization": "AgenticX Team",
        "url": "https://github.com/DemonDamon/AgenticX-DeepResearch"
    },
    "documentation_url": "https://github.com/DemonDamon/AgenticX-DeepResearch/blob/main/README.md"
}


class A2ATaskRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: Optional[str] = None
    message: Dict[str, Any] = Field(..., description="A2A Message 对象")
    metadata: Optional[Dict[str, Any]] = None


class A2ATaskResponse(BaseModel):
    id: str
    session_id: Optional[str] = None
    status: Dict[str, Any]
    artifacts: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


@router.get("/.well-known/agent.json", include_in_schema=False)
async def get_agent_card():
    """A2A Agent 发现端点（Well-Known URI）"""
    return JSONResponse(content=AGENT_CARD)


@router.post("/a2a/tasks/send", response_model=A2ATaskResponse)
async def a2a_send_task(request: A2ATaskRequest, background_tasks: BackgroundTasks):
    """A2A 协议任务委托端点"""
    parts = request.message.get("parts", [])
    topic = next((p.get("text", "") for p in parts if p.get("type") == "text"), "")

    if not topic:
        raise HTTPException(status_code=400, detail="A2A message must contain a text part with research topic")

    from db.manager import db_manager
    task_id = str(uuid.uuid4())
    db_manager.create_task(
        task_id=task_id,
        topic=topic,
        objective=f"[A2A 委托] {topic}",
        mode="advanced"
    )
    background_tasks.add_task(_execute_a2a_task, task_id, topic)

    return A2ATaskResponse(
        id=request.id,
        session_id=request.session_id,
        status={
            "state": "submitted",
            "timestamp": datetime.now().isoformat(),
            "message": {
                "role": "agent",
                "parts": [{"type": "text", "text": f"调研任务已提交，task_id: {task_id}。"}]
            }
        },
        artifacts=[],
        metadata={"internal_task_id": task_id}
    )


@router.get("/a2a/tasks/{task_id}", response_model=A2ATaskResponse)
async def a2a_get_task(task_id: str):
    """A2A 协议任务状态查询"""
    from db.manager import db_manager
    task = db_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    state_map = {"pending": "submitted", "running": "working",
                 "completed": "completed", "failed": "failed"}
    a2a_state = state_map.get(task.status, "unknown")

    artifacts = []
    if task.status == "completed" and task.result:
        artifacts.append({
            "name": "research_report",
            "description": f"关于 '{task.topic}' 的深度调研报告",
            "parts": [{"type": "text", "text": task.result}],
            "metadata": {"format": "markdown", "topic": task.topic}
        })

    return A2ATaskResponse(
        id=task_id,
        status={"state": a2a_state, "timestamp": datetime.now().isoformat()},
        artifacts=artifacts,
        metadata={"topic": task.topic, "mode": task.mode}
    )


# ═══════════════════════════════════════════════════════════════════
# 2. MCP Server 协议（兼容 IronClaw / NEAR AI Cloud）
# ═══════════════════════════════════════════════════════════════════

class MCPToolCallRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Any = None
    method: str
    params: Optional[Dict[str, Any]] = None


class MCPToolCallResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Any = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


MCP_TOOLS_MANIFEST = {
    "tools": [
        {
            "name": "deep_research",
            "description": "对指定主题进行深度调研，返回结构化研究报告。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "调研主题"},
                    "objective": {"type": "string", "description": "调研目标（可选）"},
                    "mode": {
                        "type": "string",
                        "enum": ["basic", "advanced"],
                        "description": "调研模式",
                        "default": "basic"
                    },
                    "user_id": {"type": "string", "description": "用户 ID（可选）"}
                },
                "required": ["topic"]
            }
        },
        {
            "name": "get_research_status",
            "description": "查询调研任务的执行状态和进度",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "调研任务 ID"}
                },
                "required": ["task_id"]
            }
        },
        {
            "name": "get_research_report",
            "description": "获取已完成的调研报告内容",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "调研任务 ID"}
                },
                "required": ["task_id"]
            }
        }
    ]
}


@router.get("/mcp/tools", summary="MCP 工具发现")
async def mcp_list_tools():
    """MCP 工具列表端点，供 IronClaw/NEAR AI Cloud 发现可用工具"""
    return MCP_TOOLS_MANIFEST


@router.post("/mcp/call", response_model=MCPToolCallResponse, summary="MCP 工具调用")
async def mcp_call_tool(request: MCPToolCallRequest, background_tasks: BackgroundTasks):
    """MCP 工具调用端点（JSON-RPC 2.0）"""
    if request.method != "tools/call":
        return MCPToolCallResponse(
            id=request.id,
            error={"code": -32601, "message": f"Method not found: {request.method}"}
        )

    params = request.params or {}
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name == "deep_research":
        topic = arguments.get("topic")
        if not topic:
            return MCPToolCallResponse(
                id=request.id,
                error={"code": -32602, "message": "Missing required argument: topic"}
            )
        from db.manager import db_manager
        task_id = str(uuid.uuid4())
        db_manager.create_task(
            task_id=task_id,
            topic=topic,
            objective=arguments.get("objective", f"对 {topic} 进行深度调研"),
            mode=arguments.get("mode", "basic")
        )
        background_tasks.add_task(_execute_a2a_task, task_id, topic)
        return MCPToolCallResponse(
            id=request.id,
            result={
                "content": [{"type": "text", "text": (
                    f"调研任务已创建。\ntask_id: {task_id}\n主题: {topic}\n"
                    f"请通过 GET /api/research/task/{task_id} 查询状态，"
                    f"或通过 GET /api/research/sse/{task_id} 订阅实时进度。"
                )}],
                "task_id": task_id
            }
        )

    elif tool_name == "get_research_status":
        task_id = arguments.get("task_id")
        if not task_id:
            return MCPToolCallResponse(
                id=request.id,
                error={"code": -32602, "message": "Missing required argument: task_id"}
            )
        from db.manager import db_manager
        task = db_manager.get_task(task_id)
        if not task:
            return MCPToolCallResponse(
                id=request.id,
                error={"code": -32603, "message": f"Task not found: {task_id}"}
            )
        events = task.events or []
        last_event = events[-1] if events else {}
        return MCPToolCallResponse(
            id=request.id,
            result={
                "content": [{"type": "text", "text": f"任务状态: {task.status}"}],
                "task_id": task_id,
                "status": task.status,
                "topic": task.topic,
                "progress": last_event.get("message", ""),
                "event_count": len(events)
            }
        )

    elif tool_name == "get_research_report":
        task_id = arguments.get("task_id")
        if not task_id:
            return MCPToolCallResponse(
                id=request.id,
                error={"code": -32602, "message": "Missing required argument: task_id"}
            )
        from db.manager import db_manager
        task = db_manager.get_task(task_id)
        if not task:
            return MCPToolCallResponse(
                id=request.id,
                error={"code": -32603, "message": f"Task not found: {task_id}"}
            )
        if task.status != "completed":
            return MCPToolCallResponse(
                id=request.id,
                result={
                    "content": [{"type": "text", "text": f"任务尚未完成，当前状态: {task.status}"}],
                    "status": task.status
                }
            )
        return MCPToolCallResponse(
            id=request.id,
            result={
                "content": [{"type": "text", "text": task.result or "报告内容为空"}],
                "task_id": task_id,
                "topic": task.topic,
                "status": "completed"
            }
        )

    else:
        return MCPToolCallResponse(
            id=request.id,
            error={"code": -32601, "message": f"Unknown tool: {tool_name}"}
        )


# ═══════════════════════════════════════════════════════════════════
# 3. NEAR AI Cloud Webhook（基于 HTTP 回调）
# ═══════════════════════════════════════════════════════════════════

class NearWebhookRequest(BaseModel):
    event_type: str = Field(..., description="事件类型: task_request | status_query")
    agent_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    callback_url: Optional[str] = None


@router.post("/near/webhook", summary="NEAR AI Cloud Webhook")
async def near_webhook(request: NearWebhookRequest, background_tasks: BackgroundTasks):
    """NEAR AI Cloud Webhook 端点"""
    if request.event_type == "task_request":
        topic = request.payload.get("topic", "")
        if not topic:
            raise HTTPException(status_code=400, detail="Payload must contain 'topic'")

        from db.manager import db_manager
        task_id = str(uuid.uuid4())
        db_manager.create_task(
            task_id=task_id,
            topic=topic,
            objective=request.payload.get("objective", f"[NEAR] {topic}"),
            mode=request.payload.get("mode", "advanced")
        )

        if request.callback_url:
            background_tasks.add_task(_execute_and_callback, task_id, topic, request.callback_url)
        else:
            background_tasks.add_task(_execute_a2a_task, task_id, topic)

        return {
            "status": "accepted",
            "task_id": task_id,
            "message": f"调研任务已接受，agent_id: {request.agent_id}",
            "sse_url": f"/api/research/sse/{task_id}"
        }

    elif request.event_type == "status_query":
        task_id = request.payload.get("task_id")
        if not task_id:
            raise HTTPException(status_code=400, detail="Payload must contain 'task_id'")
        from db.manager import db_manager
        task = db_manager.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "task_id": task_id,
            "status": task.status,
            "topic": task.topic,
            "has_result": bool(task.result)
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unknown event_type: {request.event_type}")


# ═══════════════════════════════════════════════════════════════════
# 内部辅助函数
# ═══════════════════════════════════════════════════════════════════

async def _execute_a2a_task(task_id: str, topic: str):
    """内部执行调研任务（供 A2A/MCP/Webhook 调用）"""
    try:
        from server.api import run_research_task, ResearchRequest
        req = ResearchRequest(topic=topic, mode="advanced")
        await run_research_task(task_id, req)
    except Exception as e:
        logger.error(f"A2A task {task_id} failed: {e}", exc_info=True)
        from db.manager import db_manager
        db_manager.update_task_status(task_id, "failed", error=str(e))


async def _execute_and_callback(task_id: str, topic: str, callback_url: str):
    """执行任务并在完成后通过 HTTP 回调通知 NEAR AI Cloud"""
    await _execute_a2a_task(task_id, topic)
    try:
        import aiohttp
        from db.manager import db_manager
        task = db_manager.get_task(task_id)
        payload = {
            "task_id": task_id,
            "status": task.status if task else "unknown",
            "result": task.result if task else None,
            "timestamp": datetime.now().isoformat()
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                callback_url, json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                logger.info(f"Callback to {callback_url} returned {resp.status}")
    except Exception as e:
        logger.warning(f"Callback failed for task {task_id}: {e}")
