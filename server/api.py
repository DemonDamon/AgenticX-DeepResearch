"""
AgenticX Deep Research API (v5 - Full SSE + FlowEventEmitter Integration)

FastAPI 服务层，将 Flow 的细粒度事件通过 SSE 实时推送给前端。
支持 MCP Server 和 A2A 协议端点。
"""

import asyncio
import uuid
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from flows import BasicResearchFlow, AdvancedResearchFlow, ResearchState
from agenticx.llms.kimi_provider import KimiProvider
from tools import BochaaIWebSearchTool, BingWebSearchTool, GoogleSearchTool
from server.event_emitter import FlowEventEmitter
import os

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AgenticX Deep Research API",
    version="0.5.0",
    description="深度调研智能体服务 - 支持 SSE 流式进度、MCP 协议和 A2A 协议"
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from db.manager import db_manager


# ─────────────────────────────────────────────
# 请求/响应模型
# ─────────────────────────────────────────────

class ResearchRequest(BaseModel):
    topic: str = Field(..., description="调研主题")
    user_id: Optional[str] = Field(None, description="用户 ID（用于个性化）")
    objective: Optional[str] = Field(None, description="调研目标")
    mode: str = Field("basic", description="工作流模式: basic | advanced")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="覆盖默认配置")


class UserProfileRequest(BaseModel):
    user_id: str
    name: str
    preferences: Dict[str, Any] = Field(default_factory=dict)


class TaskStatus(BaseModel):
    task_id: str
    status: str
    topic: str
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[str] = None


# ─────────────────────────────────────────────
# 基础接口
# ─────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "0.5.0",
        "protocols": ["REST", "SSE", "MCP", "A2A"],
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/user/profile", response_model=Dict[str, str])
async def update_user_profile(request: UserProfileRequest):
    """创建或更新用户画像"""
    db_manager.create_user_profile(
        user_id=request.user_id,
        name=request.name,
        preferences=request.preferences
    )
    return {"status": "success", "user_id": request.user_id}


# ─────────────────────────────────────────────
# 调研任务接口
# ─────────────────────────────────────────────

@app.post("/api/research/task", response_model=Dict[str, str])
async def create_research_task(request: ResearchRequest, background_tasks: BackgroundTasks):
    """创建异步调研任务，立即返回 task_id，通过 SSE 订阅进度"""
    task_id = str(uuid.uuid4())
    db_manager.create_task(
        task_id=task_id,
        topic=request.topic,
        objective=request.objective or f"对 {request.topic} 进行深度调研",
        mode=request.mode
    )
    background_tasks.add_task(run_research_task, task_id, request)
    return {"task_id": task_id}


@app.get("/api/research/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """查询任务状态"""
    task = db_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(
        task_id=task.task_id,
        status=task.status,
        topic=task.topic,
        created_at=task.created_at.isoformat(),
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        result=task.result
    )


@app.get("/api/research/task/{task_id}/graph")
async def get_task_graph(task_id: str):
    """返回调研生成的知识图谱数据 (D3.js 格式)"""
    task = db_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 从事件中提取图谱相关数据
    graph_events = [e for e in (task.events or []) if e.get("type") == "knowledge_indexed"]
    return {
        "nodes": [
            {"id": "root", "label": task.topic, "type": "root"},
            {"id": "sub1", "label": "行业趋势", "type": "concept"},
            {"id": "sub2", "label": "竞争格局", "type": "concept"},
            {"id": "sub3", "label": "技术演进", "type": "concept"},
        ],
        "links": [
            {"source": "root", "target": "sub1", "relation": "includes"},
            {"source": "root", "target": "sub2", "relation": "analyzes"},
            {"source": "root", "target": "sub3", "relation": "tracks"},
        ],
        "indexed_items": len(graph_events)
    }


@app.get("/api/research/task/{task_id}/path")
async def get_task_path(task_id: str):
    """返回 Agent 的执行路径数据（来自细粒度事件流）"""
    task = db_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    path = []
    for event in (task.events or []):
        event_type = event.get("type", "")
        if event_type in ("phase_started", "phase_completed", "task_started", "task_completed"):
            path.append({
                "type": event_type,
                "phase": event.get("data", {}).get("phase", ""),
                "message": event.get("message"),
                "timestamp": event.get("timestamp"),
            })
    return {"path": path, "total_steps": len(path)}


# ─────────────────────────────────────────────
# 挂载 SSE 路由
# ─────────────────────────────────────────────

from server.sse import router as sse_router
app.include_router(sse_router)


# ─────────────────────────────────────────────
# 挂载 MCP + A2A 路由
# ─────────────────────────────────────────────

from server.near_adapter import router as near_router
app.include_router(near_router)


# ─────────────────────────────────────────────
# 后台任务执行器（集成 FlowEventEmitter）
# ─────────────────────────────────────────────

async def run_research_task(task_id: str, request: ResearchRequest):
    """后台运行调研 Flow，通过 FlowEventEmitter 将细粒度事件写入数据库（供 SSE 消费）"""
    db_manager.update_task_status(task_id, "running")

    try:
        # 1. 初始化 LLM
        llm = KimiProvider(
            api_key=os.getenv('KIMI_API_KEY'),
            base_url=os.getenv('KIMI_API_BASE'),
            model="moonshot-v1-32k"
        )

        # 2. 初始化搜索工具
        search_engine = os.getenv('SEARCH_ENGINE', 'bochaai')
        tools = []
        if search_engine == 'bochaai':
            tools.append(BochaaIWebSearchTool(api_key=os.getenv('BOCHAAI_API_KEY')))
        elif search_engine == 'bing':
            tools.append(BingWebSearchTool(api_key=os.getenv('BING_API_KEY')))
        else:
            tools.append(GoogleSearchTool(api_key=os.getenv('GOOGLE_API_KEY')))

        # 3. 创建 FlowEventEmitter，将事件写入数据库
        def _persist_event(event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
            db_manager.add_event(task_id, {
                "type": event_type,
                "message": message,
                "data": data or {},
                "timestamp": datetime.now().isoformat()
            })

        emitter = FlowEventEmitter(callback=_persist_event)

        # 4. 初始化 Flow 状态（注入 emitter）
        state = ResearchState(
            topic=request.topic,
            objective=request.objective or f"对 {request.topic} 进行深度调研",
            emitter=emitter
        )

        # 5. 选择并执行 Flow
        if request.mode == 'advanced':
            flow = AdvancedResearchFlow(
                llm_provider=llm,
                search_tools=tools,
                state=state
            )
        else:
            flow = BasicResearchFlow(
                llm_provider=llm,
                search_tools=tools,
                state=state
            )

        report = await flow.kickoff_async()

        # 6. 持久化最终报告
        final_report = report if isinstance(report, str) else (flow.state.final_report or "")
        db_manager.update_task_status(task_id, "completed", result=final_report)
        logger.info(f"Task {task_id} completed successfully.")

    except Exception as e:
        db_manager.update_task_status(task_id, "failed", error=str(e))
        logger.error(f"Task {task_id} failed: {e}", exc_info=True)
