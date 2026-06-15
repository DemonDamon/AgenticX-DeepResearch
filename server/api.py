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
import os

logger = logging.getLogger(__name__)

app = FastAPI(title="AgenticX Deep Research API", version="0.4.0")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from db.manager import db_manager

class ResearchRequest(BaseModel):
    topic: str = Field(..., description="调研主题")
    objective: Optional[str] = Field(None, description="调研目标")
    mode: str = Field("basic", description="工作流模式: basic | advanced")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="覆盖默认配置")

class TaskStatus(BaseModel):
    task_id: str
    status: str
    topic: str
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[str] = None

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/api/research/task", response_model=Dict[str, str])
async def create_research_task(request: ResearchRequest, background_tasks: BackgroundTasks):
    """创建异步调研任务"""
    task_id = str(uuid.uuid4())
    db_manager.create_task(
        task_id=task_id,
        topic=request.topic,
        objective=request.objective or f"对 {request.topic} 进行深度调研",
        mode=request.mode
    )
    
    # 启动后台任务
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

# 挂载 SSE 路由
from server.sse import router as sse_router
app.include_router(sse_router)

async def run_research_task(task_id: str, request: ResearchRequest):
    """后台运行调研 Flow"""
    db_manager.update_task_status(task_id, "running")
    
    try:
        # 1. 初始化 LLM 和工具
        llm = KimiProvider(
            api_key=os.getenv('KIMI_API_KEY'),
            base_url=os.getenv('KIMI_API_BASE'),
            model="moonshot-v1-32k"
        )
        
        search_engine = os.getenv('SEARCH_ENGINE', 'bochaai')
        tools = []
        if search_engine == 'bochaai':
            tools.append(BochaaIWebSearchTool(api_key=os.getenv('BOCHAAI_API_KEY')))
        elif search_engine == 'bing':
            tools.append(BingWebSearchTool(api_key=os.getenv('BING_API_KEY')))
        else:
            tools.append(GoogleSearchTool(api_key=os.getenv('GOOGLE_API_KEY')))
            
        # 2. 初始化 Flow 状态
        state = ResearchState(
            topic=request.topic, 
            objective=request.objective or f"对 {request.topic} 进行深度调研"
        )
        
        # 3. 选择 Flow
        if request.mode == 'advanced':
            flow = AdvancedResearchFlow(llm_provider=llm, search_tools=tools, state=state)
        else:
            flow = BasicResearchFlow(llm_provider=llm, search_tools=tools, state=state)
            
        # 4. 执行并记录进度事件
        def log_event(event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
            db_manager.add_event(task_id, {
                "type": event_type,
                "message": message,
                "data": data,
                "timestamp": datetime.now().isoformat()
            })

        log_event("status_update", "正在初始化调研引擎...")
        
        # 执行 Flow
        report = await flow.kickoff_async()
        
        log_event("status_update", "调研报告生成完成")
        
        # 5. 更新状态
        db_manager.update_task_status(task_id, "completed", result=report)
        logger.info(f"Task {task_id} completed successfully.")
        
    except Exception as e:
        db_manager.update_task_status(task_id, "failed", error=str(e))
        logger.error(f"Task {task_id} failed: {e}")
