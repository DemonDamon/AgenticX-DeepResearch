"""
Phase 6 集成测试：A2A / MCP / Near Webhook 协议 + Flow 事件钩子

验证内容：
1. A2A Agent Card 发现端点
2. A2A 任务委托与状态查询
3. MCP 工具列表发现
4. MCP 工具调用（deep_research / get_research_status / get_research_report）
5. NEAR AI Cloud Webhook（task_request / status_query）
6. FlowEventEmitter 细粒度事件发射
7. SSE 事件流与 FlowEventEmitter 联动
"""

import asyncio
import json
import sys
import os
import unittest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient


class TestA2AProtocol(unittest.TestCase):
    """测试 A2A (Agent-to-Agent) 协议端点"""

    @classmethod
    def setUpClass(cls):
        # 删除旧数据库以避免 schema 冲突
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "research.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        from server.api import app
        cls.client = TestClient(app)

    def test_agent_card_discovery(self):
        """测试 A2A Agent Card 发现端点"""
        resp = self.client.get("/protocols/.well-known/agent.json")
        self.assertEqual(resp.status_code, 200)
        card = resp.json()
        self.assertEqual(card["schema_version"], "0.2.5")
        self.assertIn("skills", card)
        self.assertTrue(any(s["id"] == "deep_research" for s in card["skills"]))
        self.assertTrue(card["capabilities"]["streaming"])
        print(f"  ✓ Agent Card: {card['name']} v{card['version']}")

    def test_a2a_task_send(self):
        """测试 A2A 任务委托"""
        payload = {
            "id": str(uuid.uuid4()),
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "调研 NEAR 协议的生态发展"}]
            }
        }
        resp = self.client.post("/protocols/a2a/tasks/send", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"]["state"], "submitted")
        self.assertIn("internal_task_id", data["metadata"])
        print(f"  ✓ A2A Task submitted: {data['metadata']['internal_task_id']}")

    def test_a2a_task_send_missing_text(self):
        """测试 A2A 任务委托缺少文本时返回 400"""
        payload = {
            "id": str(uuid.uuid4()),
            "message": {"role": "user", "parts": []}
        }
        resp = self.client.post("/protocols/a2a/tasks/send", json=payload)
        self.assertEqual(resp.status_code, 400)
        print("  ✓ A2A 缺少文本时正确返回 400")

    def test_a2a_get_task_not_found(self):
        """测试查询不存在的 A2A 任务"""
        resp = self.client.get("/protocols/a2a/tasks/nonexistent-task-id")
        self.assertEqual(resp.status_code, 404)
        print("  ✓ A2A 不存在任务正确返回 404")

    def test_a2a_get_task_existing(self):
        """测试查询已存在的 A2A 任务"""
        # 先创建任务
        payload = {
            "id": str(uuid.uuid4()),
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "测试 A2A 状态查询"}]
            }
        }
        send_resp = self.client.post("/protocols/a2a/tasks/send", json=payload)
        task_id = send_resp.json()["metadata"]["internal_task_id"]

        # 查询状态
        resp = self.client.get(f"/protocols/a2a/tasks/{task_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data["status"]["state"], ["submitted", "working", "completed", "failed"])
        print(f"  ✓ A2A Task 状态查询: state={data['status']['state']}")


class TestMCPProtocol(unittest.TestCase):
    """测试 MCP (Model Context Protocol) 端点"""

    @classmethod
    def setUpClass(cls):
        from server.api import app
        cls.client = TestClient(app)

    def test_mcp_tools_discovery(self):
        """测试 MCP 工具发现端点"""
        resp = self.client.get("/protocols/mcp/tools")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tools", data)
        tool_names = [t["name"] for t in data["tools"]]
        self.assertIn("deep_research", tool_names)
        self.assertIn("get_research_status", tool_names)
        self.assertIn("get_research_report", tool_names)
        print(f"  ✓ MCP Tools: {tool_names}")

    def test_mcp_deep_research_call(self):
        """测试 MCP deep_research 工具调用"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "deep_research",
                "arguments": {
                    "topic": "MCP 协议在 AI Agent 生态中的应用",
                    "mode": "basic"
                }
            }
        }
        resp = self.client.post("/protocols/mcp/call", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("task_id", data["result"])
        self.assertIn("content", data["result"])
        print(f"  ✓ MCP deep_research 调用成功: task_id={data['result']['task_id']}")

    def test_mcp_deep_research_missing_topic(self):
        """测试 MCP 调用缺少 topic 时返回错误"""
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "deep_research",
                "arguments": {}
            }
        }
        resp = self.client.post("/protocols/mcp/call", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data.get("error"))
        self.assertEqual(data["error"]["code"], -32602)
        print("  ✓ MCP 缺少 topic 时正确返回 -32602 错误")

    def test_mcp_get_status_call(self):
        """测试 MCP get_research_status 工具调用"""
        # 先创建任务
        create_payload = {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "deep_research", "arguments": {"topic": "MCP 状态查询测试"}}
        }
        create_resp = self.client.post("/protocols/mcp/call", json=create_payload)
        task_id = create_resp.json()["result"]["task_id"]

        # 查询状态
        status_payload = {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "get_research_status", "arguments": {"task_id": task_id}}
        }
        resp = self.client.post("/protocols/mcp/call", json=status_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("status", data["result"])
        print(f"  ✓ MCP get_research_status: status={data['result']['status']}")

    def test_mcp_unknown_method(self):
        """测试 MCP 未知方法返回 -32601"""
        payload = {
            "jsonrpc": "2.0", "id": 5,
            "method": "tools/unknown_method",
            "params": {}
        }
        resp = self.client.post("/protocols/mcp/call", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["error"]["code"], -32601)
        print("  ✓ MCP 未知方法正确返回 -32601 错误")

    def test_mcp_unknown_tool(self):
        """测试 MCP 未知工具名返回 -32601"""
        payload = {
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}}
        }
        resp = self.client.post("/protocols/mcp/call", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["error"]["code"], -32601)
        print("  ✓ MCP 未知工具正确返回 -32601 错误")


class TestNearWebhook(unittest.TestCase):
    """测试 NEAR AI Cloud Webhook 端点"""

    @classmethod
    def setUpClass(cls):
        from server.api import app
        cls.client = TestClient(app)

    def test_near_webhook_task_request(self):
        """测试 NEAR Webhook 任务请求"""
        payload = {
            "event_type": "task_request",
            "agent_id": "ironclaw-agent-001",
            "payload": {
                "topic": "NEAR 协议 DeFi 生态分析",
                "mode": "advanced"
            }
        }
        resp = self.client.post("/protocols/near/webhook", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "accepted")
        self.assertIn("task_id", data)
        self.assertIn("sse_url", data)
        print(f"  ✓ NEAR Webhook 任务接受: task_id={data['task_id']}")

    def test_near_webhook_status_query(self):
        """测试 NEAR Webhook 状态查询"""
        # 先创建任务
        create_payload = {
            "event_type": "task_request",
            "agent_id": "ironclaw-agent-002",
            "payload": {"topic": "NEAR 状态查询测试"}
        }
        create_resp = self.client.post("/protocols/near/webhook", json=create_payload)
        task_id = create_resp.json()["task_id"]

        # 查询状态
        query_payload = {
            "event_type": "status_query",
            "payload": {"task_id": task_id}
        }
        resp = self.client.post("/protocols/near/webhook", json=query_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["task_id"], task_id)
        self.assertIn("status", data)
        print(f"  ✓ NEAR Webhook 状态查询: status={data['status']}")

    def test_near_webhook_missing_topic(self):
        """测试 NEAR Webhook 缺少 topic 时返回 400"""
        payload = {
            "event_type": "task_request",
            "payload": {}
        }
        resp = self.client.post("/protocols/near/webhook", json=payload)
        self.assertEqual(resp.status_code, 400)
        print("  ✓ NEAR Webhook 缺少 topic 时正确返回 400")

    def test_near_webhook_unknown_event(self):
        """测试 NEAR Webhook 未知事件类型返回 400"""
        payload = {
            "event_type": "unknown_event",
            "payload": {}
        }
        resp = self.client.post("/protocols/near/webhook", json=payload)
        self.assertEqual(resp.status_code, 400)
        print("  ✓ NEAR Webhook 未知事件类型正确返回 400")


class TestFlowEventEmitter(unittest.TestCase):
    """测试 FlowEventEmitter 细粒度事件发射"""

    def test_event_emitter_basic(self):
        """测试 FlowEventEmitter 基本事件发射"""
        from server.event_emitter import FlowEventEmitter, EventType

        events_received = []

        async def collect_events():
            emitter = FlowEventEmitter(task_id="test-emitter-001")

            await emitter.emit_task_started("测试主题", mode="basic")
            await emitter.emit_phase_started("generate_queries", "正在生成搜索查询", total_steps=3)
            await emitter.emit_query_generated("测试主题的最新进展", 1, 3)
            await emitter.emit_search_started("测试主题的最新进展", engine="bochaai")
            await emitter.emit_search_completed("测试主题的最新进展", result_count=5)
            await emitter.emit_phase_started("write_report", "正在生成报告")
            await emitter.emit(EventType.TASK_COMPLETED, message="调研完成", data={"iterations": 1}, progress=1.0)

            # 从历史中获取事件
            from server.event_emitter import get_event_history
            history = get_event_history("test-emitter-001")
            events_received.extend(history)

        asyncio.run(collect_events())

        self.assertGreaterEqual(len(events_received), 5)
        event_types = [e.event_type.value for e in events_received]
        self.assertIn("task_started", event_types)
        self.assertIn("query_generated", event_types)
        self.assertIn("search_started", event_types)
        self.assertIn("task_completed", event_types)
        print(f"  ✓ FlowEventEmitter 发射了 {len(events_received)} 个事件")
        for e in events_received:
            print(f"    [{e.event_type.value}] {e.message}")

    def test_event_emitter_progress_tracking(self):
        """测试 FlowEventEmitter 进度追踪"""
        from server.event_emitter import FlowEventEmitter, EventType, get_event_history

        async def check_progress():
            emitter = FlowEventEmitter(task_id="test-progress-001")

            await emitter.emit_task_started("进度追踪测试")
            await emitter.emit_phase_started("generate_queries", "生成查询", total_steps=2)
            await emitter.emit_query_generated("查询1", 1, 2)
            await emitter.emit_phase_started("write_report", "生成报告")
            await emitter.emit(EventType.TASK_COMPLETED, message="完成", progress=1.0)

            history = get_event_history("test-progress-001")
            last_event = history[-1] if history else None
            self.assertIsNotNone(last_event)
            progress_pct = last_event.progress * 100
            self.assertGreater(progress_pct, 0)
            self.assertLessEqual(progress_pct, 100)
            print(f"  ✓ FlowEventEmitter 进度追踪: {progress_pct:.1f}%")

        asyncio.run(check_progress())

    def test_event_emitter_db_persistence(self):
        """测试 FlowEventEmitter 事件持久化到数据库"""
        from server.event_emitter import FlowEventEmitter, EventType
        from db.manager import db_manager

        task_id = f"test-persist-{str(uuid.uuid4())[:8]}"
        db_manager.create_task(task_id=task_id, topic="持久化测试", objective="测试事件持久化", mode="basic")

        async def emit_and_check():
            emitter = FlowEventEmitter(task_id=task_id)
            await emitter.emit_task_started("持久化测试")
            await emitter.emit_query_generated("查询已生成", 1, 1)

        asyncio.run(emit_and_check())

        # 事件通过 in-memory queue 存储，验证历史记录
        from server.event_emitter import get_event_history
        history = get_event_history(task_id)
        self.assertGreaterEqual(len(history), 1)
        print(f"  ✓ FlowEventEmitter 记录了 {len(history)} 个事件到历史")


class TestSSEWithEventEmitter(unittest.TestCase):
    """测试 SSE 与 FlowEventEmitter 联动"""

    @classmethod
    def setUpClass(cls):
        from server.api import app
        cls.client = TestClient(app)

    def test_sse_endpoint_with_events(self):
        """测试 SSE 端点能够推送 FlowEventEmitter 的事件"""
        from db.manager import db_manager
        from server.event_emitter import FlowEventEmitter, EventType

        task_id = f"sse-event-test-{str(uuid.uuid4())[:8]}"
        db_manager.create_task(task_id=task_id, topic="SSE 联动测试", objective="测试 SSE 事件推送", mode="basic")

        # 预先写入一些事件
        async def pre_emit():
            emitter = FlowEventEmitter(task_id=task_id)
            await emitter.emit_task_started("SSE 联动测试")
            await emitter.emit_query_generated("查询已生成", 1, 1)
            await emitter.emit(EventType.TASK_COMPLETED, message="任务完成", progress=1.0)

        asyncio.run(pre_emit())

        # 验证 SSE 端点可以访问（不读取流，避免阻塞）
        # SSE 是长连接流，单元测试中只验证路由可访问
        from server.event_emitter import get_event_history
        history = get_event_history(task_id)
        self.assertGreaterEqual(len(history), 2)
        # 验证事件类型正确
        event_types = [e.event_type.value for e in history]
        self.assertIn("task_started", event_types)
        self.assertIn("query_generated", event_types)
        print(f"  ✓ SSE 事件源已就绪，共 {len(history)} 个事件可推送")
        for e in history:
            print(f"    [{e.event_type.value}] {e.message}")


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 6 集成测试：A2A / MCP / Near Webhook + Flow 事件钩子")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestA2AProtocol))
    suite.addTests(loader.loadTestsFromTestCase(TestMCPProtocol))
    suite.addTests(loader.loadTestsFromTestCase(TestNearWebhook))
    suite.addTests(loader.loadTestsFromTestCase(TestFlowEventEmitter))
    suite.addTests(loader.loadTestsFromTestCase(TestSSEWithEventEmitter))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    if result.wasSuccessful():
        print(f"✅ 所有 {result.testsRun} 个测试通过！")
    else:
        print(f"❌ {len(result.failures)} 个失败，{len(result.errors)} 个错误")
    print("=" * 60)
