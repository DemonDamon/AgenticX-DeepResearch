from sqlalchemy.orm import Session
from .models import ResearchTask, SessionLocal, init_db
from datetime import datetime
from typing import List, Optional, Dict, Any

class DBManager:
    def __init__(self):
        init_db()

    def create_task(self, task_id: str, topic: str, objective: str, mode: str) -> ResearchTask:
        db = SessionLocal()
        task = ResearchTask(
            task_id=task_id,
            topic=topic,
            objective=objective,
            mode=mode,
            status="pending",
            events=[]
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        db.close()
        return task

    def update_task_status(self, task_id: str, status: str, result: Optional[str] = None, error: Optional[str] = None):
        db = SessionLocal()
        task = db.query(ResearchTask).filter(ResearchTask.task_id == task_id).first()
        if task:
            task.status = status
            if result:
                task.result = result
                task.completed_at = datetime.utcnow()
            if error:
                task.error = error
            db.commit()
        db.close()

    def add_event(self, task_id: str, event: Dict[str, Any]):
        db = SessionLocal()
        task = db.query(ResearchTask).filter(ResearchTask.task_id == task_id).first()
        if task:
            # SQLAlchemy 对于 JSON 类型的更新需要手动标记或重新赋值
            events = list(task.events or [])
            events.append(event)
            task.events = events
            db.commit()
        db.close()

    def get_task(self, task_id: str) -> Optional[ResearchTask]:
        db = SessionLocal()
        task = db.query(ResearchTask).filter(ResearchTask.task_id == task_id).first()
        db.close()
        return task

    def list_tasks(self, limit: int = 10) -> List[ResearchTask]:
        db = SessionLocal()
        tasks = db.query(ResearchTask).order_by(ResearchTask.created_at.desc()).limit(limit).all()
        db.close()
        return tasks

db_manager = DBManager()
