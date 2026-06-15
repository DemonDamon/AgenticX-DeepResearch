import os
import json
import unittest
import uuid
from fastapi.testclient import TestClient
from server.api import app
from db.manager import db_manager
from tools.multimodal_doc import MultimodalDocTool

class TestPhase5Evolution(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        # 确保数据库环境干净
        if os.path.exists("research.db"):
            # 简单清理，生产中应使用独立的测试数据库
            pass

    def test_multimodal_tool(self):
        """测试多模态文档解析工具"""
        tool = MultimodalDocTool()
        # 模拟解析一个不存在的文件（测试路径处理）
        import asyncio
        result = asyncio.run(tool._arun("test.pdf", query="行业趋势"))
        self.assertIn("Error: File not found", result)
        
        # 验证 Schema
        schema = tool.to_function_schema()
        # BaseTool 默认使用类名
        self.assertEqual(schema["name"], "MultimodalDocTool")
        self.assertIn("file_path", schema["parameters"]["required"])

    def test_user_profile_api(self):
        """测试用户画像 API"""
        user_id = "user_" + str(uuid.uuid4())
        payload = {
            "user_id": user_id,
            "name": "Damon",
            "preferences": {"depth": "high", "focus": ["tech"]}
        }
        response = self.client.post("/api/user/profile", json=payload)
        self.assertEqual(response.status_code, 200)
        
        # 验证数据库记录
        profile = db_manager.get_user_profile(user_id)
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "Damon")
        self.assertEqual(profile.preferences["depth"], "high")

    def test_visualization_endpoints(self):
        """测试可视化数据接口"""
        task_id = "task_" + str(uuid.uuid4())
        db_manager.create_task(task_id, "Visual Test", "Test", "basic")
        
        # 测试图谱接口
        response = self.client.get(f"/api/research/task/{task_id}/graph")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("nodes", data)
        self.assertIn("links", data)
        
        # 测试路径接口
        response = self.client.get(f"/api/research/task/{task_id}/path")
        self.assertEqual(response.status_code, 200)
        path_data = response.json()
        self.assertIn("path", path_data)

if __name__ == "__main__":
    unittest.main()
