from sqlalchemy import Column, String, Text, DateTime, JSON, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class ResearchTask(Base):
    __tablename__ = "research_tasks"
    
    task_id = Column(String(36), primary_key=True)
    topic = Column(String(255), nullable=False)
    objective = Column(Text)
    mode = Column(String(20), default="basic")
    status = Column(String(20), default="pending")
    result = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    events = Column(JSON, default=list)

# 数据库连接配置
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "research.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
