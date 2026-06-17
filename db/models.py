from sqlalchemy import Column, String, Text, DateTime, JSON, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    user_id = Column(String(36), primary_key=True)
    name = Column(String(100))
    preferences = Column(JSON, default=dict) # 存储调研偏好，如 {"depth": "high", "focus": ["tech", "market"]}
    interests = Column(JSON, default=list) # 关注的领域列表
    created_at = Column(DateTime, default=datetime.utcnow)

class ResearchTask(Base):
    __tablename__ = "research_tasks"
    
    task_id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("user_profiles.user_id"), nullable=True)
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
    # Tests may delete the sqlite file after this module has been imported.
    # Disposing stale connections prevents "readonly database" handles.
    engine.dispose()
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
