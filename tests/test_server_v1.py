import os
import json
import asyncio
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

# 设置 Mock 环境
os.environ["KIMI_API_KEY"] = "mock_key"
os.environ["BOCHAAI_API_KEY"] = "mock_key"

from server.api import app
from db.manager import db_manager

class TestServerV1(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check(self):
        """测试健康检查接口"""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertIn("status", response.json())
        self.assertEqual(response.json()["status"], "healthy")

    @patch("server.api.run_research_task")
    def test_create_task(self, mock_run):
        """测试创建任务接口"""
        payload = {
            "topic": "AI Agent Protocols",
            "objective": "调研最前沿的 Agent 协议",
            "mode": "basic"
        }
        response = self.client.post("/api/research/task", json=payload)
        self.assertEqual(response.status_code, 200)
        task_id = response.json().get("task_id")
        self.assertIsNotNone(task_id)
        
        # 验证数据库记录
        task = db_manager.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task.topic, "AI Agent Protocols")
        self.assertEqual(task.status, "pending")

    def test_get_task_status_404(self):
        """测试查询不存在的任务"""
        response = self.client.get("/api/research/task/non_existent_id")
        self.assertEqual(response.status_code, 404)

    def test_sse_endpoint_basic(self):
        """测试 SSE 接口连接"""
        # 创建一个测试任务
        import uuid
        task_id = "test_sse_" + str(uuid.uuid4())
        db_manager.create_task(task_id, "SSE Test", "Test", "basic")
        db_manager.add_event(task_id, {"type": "test", "message": "Hello SSE"})
        
        # 使用 TestClient 模拟 SSE 请求
        # 注意：TestClient 处理流式响应的方式略有不同
        with self.client.stream("GET", f"/api/research/task/{task_id}/events") as response:
            self.assertEqual(response.status_code, 200)
            # 读取第一行数据
            for line in response.iter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:])
                    self.assertEqual(data["type"], "test")
                    self.assertEqual(data["message"], "Hello SSE")
                    break

if __name__ == "__main__":
    unittest.main()
