import asyncio
import json
import logging
import os
from typing import AsyncGenerator, Dict, Any
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# 这是一个全局引用，将在 api.py 中初始化
_tasks_ref: Dict[str, Any] = {}

def set_tasks_ref(tasks_dict: Dict[str, Any]):
    global _tasks_ref
    _tasks_ref.update(tasks_dict)
    # 注意：直接 update 可能不会同步引用，api.py 应该直接修改这个全局字典

@router.get("/api/research/task/{task_id}/events")
async def task_events(task_id: str, request: Request):
    """
    SSE 接口：流式推送调研任务的实时进度
    """
    from db.manager import db_manager
    
    task = db_manager.get_task(task_id)
    if not task:
        return {"error": "Task not found"}

    async def event_generator() -> AsyncGenerator[Dict[str, Any], None]:
        last_event_idx = 0
        
        while True:
            if await request.is_disconnected():
                logger.info(f"Client disconnected from task {task_id} events")
                break

            # 每次轮询重新从数据库获取最新状态
            current_task = db_manager.get_task(task_id)
            if not current_task:
                break

            current_events = current_task.events or []
            if len(current_events) > last_event_idx:
                for i in range(last_event_idx, len(current_events)):
                    event = current_events[i]
                    yield {"data": json.dumps(event, ensure_ascii=False)}
                last_event_idx = len(current_events)
                if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("AGENTICX_DISABLE_BACKGROUND_TASKS") == "1":
                    break

            if current_task.status in ["completed", "failed"]:
                # 检查是否还有未发送的事件
                if len(current_events) <= last_event_idx:
                    final_event = {
                        "type": "status_update",
                        "status": current_task.status,
                        "message": "调研任务已结束" if current_task.status == "completed" else f"调研任务失败: {current_task.error}"
                    }
                    yield {"data": json.dumps(final_event, ensure_ascii=False)}
                    break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())
