"""
Flow Event Emitter - 细粒度事件钩子系统
=========================================
为 AgenticX-DeepResearch 的 Flow 执行过程提供细粒度的事件发射能力。
所有事件均通过 asyncio.Queue 传递，SSE 层订阅并推送给前端。

事件类型 (EventType):
  - TASK_STARTED       : 任务开始
  - PHASE_STARTED      : 阶段开始（如"生成查询"、"执行搜索"）
  - PHASE_COMPLETED    : 阶段完成
  - QUERY_GENERATED    : 单条查询生成
  - SEARCH_STARTED     : 单次搜索开始
  - SEARCH_COMPLETED   : 单次搜索完成（含结果数量）
  - SUMMARY_GENERATED  : 单段摘要生成
  - ITERATION_COMPLETED: 一轮迭代完成
  - PLAN_PATCHED       : AdaptivePlanner 修补执行计划
  - KNOWLEDGE_INDEXED  : 知识入库
  - REPORT_STARTED     : 报告撰写开始
  - REPORT_COMPLETED   : 报告撰写完成
  - TASK_COMPLETED     : 任务完成
  - TASK_FAILED        : 任务失败
  - HEARTBEAT          : 心跳（防止 SSE 超时）
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Awaitable
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    TASK_STARTED = "task_started"
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    QUERY_GENERATED = "query_generated"
    SEARCH_STARTED = "search_started"
    SEARCH_COMPLETED = "search_completed"
    SUMMARY_GENERATED = "summary_generated"
    ITERATION_COMPLETED = "iteration_completed"
    PLAN_PATCHED = "plan_patched"
    KNOWLEDGE_INDEXED = "knowledge_indexed"
    REPORT_STARTED = "report_started"
    REPORT_COMPLETED = "report_completed"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    HEARTBEAT = "heartbeat"


class FlowEvent(BaseModel):
    """单个 Flow 执行事件"""
    task_id: str
    event_type: EventType
    phase: str = ""          # 当前阶段名称（如 "generate_queries"）
    message: str = ""        # 人类可读的进度描述
    data: Dict[str, Any] = Field(default_factory=dict)  # 附加结构化数据
    progress: float = 0.0    # 0.0 ~ 1.0 整体进度
    timestamp: float = Field(default_factory=time.time)

    def to_sse_dict(self) -> Dict[str, Any]:
        """转换为 SSE 推送格式"""
        return {
            "task_id": self.task_id,
            "type": self.event_type.value,
            "phase": self.phase,
            "message": self.message,
            "data": self.data,
            "progress": round(self.progress, 3),
            "timestamp": self.timestamp,
        }


# 全局事件队列注册表：task_id -> asyncio.Queue
_event_queues: Dict[str, asyncio.Queue] = {}
# 持久化事件历史：task_id -> List[FlowEvent]（用于 SSE 断线重连）
_event_history: Dict[str, List[FlowEvent]] = {}


def get_or_create_queue(task_id: str) -> asyncio.Queue:
    """获取或创建任务的事件队列"""
    if task_id not in _event_queues:
        _event_queues[task_id] = asyncio.Queue()
        _event_history[task_id] = []
    return _event_queues[task_id]


def get_event_history(task_id: str) -> List[FlowEvent]:
    """获取任务的历史事件（用于 SSE 断线重连补发）"""
    return _event_history.get(task_id, [])


def cleanup_task(task_id: str):
    """清理任务的事件队列（任务完成后调用）"""
    _event_queues.pop(task_id, None)
    # 保留历史，供后续查询


class FlowEventEmitter:
    """
    Flow 事件发射器
    注入到 Flow 中，在每个关键步骤发射细粒度事件。
    
    使用方式：
        emitter = FlowEventEmitter(task_id="xxx")
        await emitter.emit(EventType.PHASE_STARTED, phase="generate_queries", message="正在生成搜索查询...")
    """

    # 各阶段的预设进度权重（总和 = 1.0）
    PHASE_PROGRESS = {
        "generate_queries":       (0.00, 0.10),   # 0% ~ 10%
        "search_and_summarize":   (0.10, 0.60),   # 10% ~ 60%
        "adaptive_planning":      (0.60, 0.70),   # 60% ~ 70%（Advanced 模式）
        "write_report":           (0.70, 0.95),   # 70% ~ 95%
        "knowledge_indexing":     (0.95, 1.00),   # 95% ~ 100%
    }

    def __init__(self, task_id: str, on_event: Optional[Callable[[FlowEvent], Awaitable[None]]] = None):
        self.task_id = task_id
        self.queue = get_or_create_queue(task_id)
        self._on_event = on_event  # 可选的额外回调（如写数据库）
        self._current_phase = ""
        self._phase_step = 0       # 当前阶段内的步骤计数
        self._phase_total = 1      # 当前阶段内的总步骤数

    async def emit(
        self,
        event_type: EventType,
        phase: str = "",
        message: str = "",
        data: Optional[Dict[str, Any]] = None,
        progress: Optional[float] = None,
    ) -> None:
        """发射一个事件"""
        if phase:
            self._current_phase = phase

        # 自动计算进度
        if progress is None:
            progress = self._calculate_progress(event_type)

        event = FlowEvent(
            task_id=self.task_id,
            event_type=event_type,
            phase=self._current_phase,
            message=message,
            data=data or {},
            progress=progress,
        )

        # 存入历史
        if self.task_id in _event_history:
            _event_history[self.task_id].append(event)

        # 放入队列（供 SSE 消费）
        await self.queue.put(event)

        # 调用额外回调（如数据库写入）
        if self._on_event:
            try:
                await self._on_event(event)
            except Exception as e:
                logger.warning(f"Event callback failed: {e}")

        logger.debug(f"[{self.task_id}] Event: {event_type.value} | {message}")

    def _calculate_progress(self, event_type: EventType) -> float:
        """根据当前阶段和事件类型自动计算进度"""
        phase_range = self.PHASE_PROGRESS.get(self._current_phase, (0.0, 1.0))
        start, end = phase_range

        if event_type in (EventType.PHASE_STARTED, EventType.TASK_STARTED):
            return start
        elif event_type in (EventType.PHASE_COMPLETED, EventType.ITERATION_COMPLETED):
            return end
        elif event_type == EventType.TASK_COMPLETED:
            return 1.0
        elif event_type == EventType.TASK_FAILED:
            return self._last_progress if hasattr(self, '_last_progress') else 0.0
        else:
            # 阶段内插值
            if self._phase_total > 0:
                step_ratio = min(self._phase_step / self._phase_total, 1.0)
            else:
                step_ratio = 0.5
            return start + (end - start) * step_ratio

    def set_phase_steps(self, total: int):
        """设置当前阶段的总步骤数（用于进度插值）"""
        self._phase_total = max(total, 1)
        self._phase_step = 0

    def advance_step(self):
        """推进当前阶段的步骤计数"""
        self._phase_step = min(self._phase_step + 1, self._phase_total)

    async def emit_heartbeat(self):
        """发射心跳事件（防止 SSE 连接超时）"""
        await self.emit(
            EventType.HEARTBEAT,
            message="♥",
            progress=self._calculate_progress(EventType.HEARTBEAT)
        )

    async def emit_task_started(self, topic: str, mode: str = "basic"):
        await self.emit(
            EventType.TASK_STARTED,
            phase="initialize",
            message=f"开始深度调研：{topic}",
            data={"topic": topic, "mode": mode},
            progress=0.0
        )

    async def emit_phase_started(self, phase: str, message: str, total_steps: int = 1):
        self.set_phase_steps(total_steps)
        await self.emit(EventType.PHASE_STARTED, phase=phase, message=message)

    async def emit_phase_completed(self, phase: str, message: str):
        await self.emit(EventType.PHASE_COMPLETED, phase=phase, message=message)

    async def emit_query_generated(self, query: str, index: int, total: int):
        self.advance_step()
        await self.emit(
            EventType.QUERY_GENERATED,
            message=f"生成查询 [{index}/{total}]：{query}",
            data={"query": query, "index": index, "total": total}
        )

    async def emit_search_started(self, query: str, engine: str = ""):
        await self.emit(
            EventType.SEARCH_STARTED,
            message=f"搜索中：{query}",
            data={"query": query, "engine": engine}
        )

    async def emit_search_completed(self, query: str, result_count: int):
        self.advance_step()
        await self.emit(
            EventType.SEARCH_COMPLETED,
            message=f"搜索完成：找到 {result_count} 条结果",
            data={"query": query, "result_count": result_count}
        )

    async def emit_summary_generated(self, query: str, summary_length: int):
        await self.emit(
            EventType.SUMMARY_GENERATED,
            message=f"摘要生成完成（{summary_length} 字符）",
            data={"query": query, "summary_length": summary_length}
        )

    async def emit_plan_patched(self, patch_description: str, added_tasks: int = 0):
        await self.emit(
            EventType.PLAN_PATCHED,
            phase="adaptive_planning",
            message=f"动态规划更新：{patch_description}",
            data={"patch_description": patch_description, "added_tasks": added_tasks}
        )

    async def emit_knowledge_indexed(self, doc_count: int):
        await self.emit(
            EventType.KNOWLEDGE_INDEXED,
            phase="knowledge_indexing",
            message=f"知识入库完成：{doc_count} 条文档",
            data={"doc_count": doc_count}
        )

    async def emit_report_started(self):
        await self.emit(
            EventType.REPORT_STARTED,
            phase="write_report",
            message="开始撰写深度调研报告..."
        )

    async def emit_report_completed(self, report_length: int):
        await self.emit(
            EventType.REPORT_COMPLETED,
            phase="write_report",
            message=f"报告撰写完成（{report_length} 字符）",
            data={"report_length": report_length},
            progress=0.95
        )

    async def emit_task_completed(self, task_id: str, report_preview: str = ""):
        await self.emit(
            EventType.TASK_COMPLETED,
            message="深度调研任务完成！",
            data={
                "task_id": task_id,
                "report_preview": report_preview[:200] if report_preview else ""
            },
            progress=1.0
        )

    async def emit_task_failed(self, error: str):
        await self.emit(
            EventType.TASK_FAILED,
            message=f"任务执行失败：{error}",
            data={"error": error}
        )
