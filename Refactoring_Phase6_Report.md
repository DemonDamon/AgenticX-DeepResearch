# AgenticX-DeepResearch 第六阶段重构报告：协议适配与流式钩子优化

**作者：** Manus AI
**日期：** 2026-06-15

## 1. 核心目标
本阶段致力于将 `AgenticX-DeepResearch` 从本地工具转化为一个标准的、可互操作的 AI 服务。主要解决了两个关键痛点：
1. **协议孤岛问题**：之前的服务只提供了自定义的 REST 接口，无法与业界主流的 Agent 编排框架（如 NEAR AI、Claude Desktop 等）无缝对接。
2. **进度黑盒问题**：之前的 SSE 只能粗粒度地反馈任务状态，用户无法感知 Agent 内部的“思考”与“执行”细节。

## 2. 核心架构演进

### 2.1 三协议统一适配层 (Tri-Protocol Adapter)
针对 2026 年的 Agent 互联生态现状（旧版 nearai SDK 已废弃），我们重新设计了 `NearAdapter`，使其成为一个**三协议统一适配层**，同时支持：

1. **A2A (Agent-to-Agent) 协议**
   - 实现了 Google 发布的 A2A 开放标准 [1]。
   - 提供 `/.well-known/agent.json` 端点，暴露 Agent Card（包含 `deep_research` 技能声明）。
   - 提供 `/protocols/a2a/tasks/send` 端点，支持接收标准化消息并转换为内部的调研任务。

2. **MCP (Model Context Protocol)**
   - 实现了 Anthropic 提出的 MCP 标准 [2]。
   - 将调研能力暴露为 `deep_research`、`get_research_status` 和 `get_research_report` 三个标准 Tool。
   - 允许任何支持 MCP 的宿主（如 NEAR AI IronClaw、Claude Desktop、Cursor）直接将本系统作为其工具链的一部分。

3. **NEAR Webhook**
   - 针对 NEAR AI Cloud 的特定场景，保留了基于 Webhook 的异步任务触发和状态查询机制。

### 2.2 细粒度事件钩子 (FlowEventEmitter)
为了彻底解决“进度黑盒”问题，我们引入了 `FlowEventEmitter` 组件：

- **深度注入 Flow 引擎**：在 `BasicResearchFlow` 和 `AdvancedResearchFlow` 的每一个关键节点（如生成查询、执行搜索、分析结果、撰写报告）注入了事件发射器。
- **自动进度计算**：基于预设的权重（如搜索占 50%，写报告占 25%），自动计算出 0.0 到 1.0 的平滑进度值。
- **内存队列与持久化双写**：事件不仅实时写入 `asyncio.Queue` 供 SSE 长连接消费，还同步持久化到 SQLite 数据库，支持断线重连后的事件补发。

## 3. 测试验证
我们编写了全面的集成测试套件 `test_phase6_protocols.py`，覆盖了 19 个测试用例。

**测试结果亮点：**
- **A2A 协议**：成功验证了 Agent Card 发现、任务委托和状态查询。
- **MCP 协议**：成功验证了工具列表发现和 JSON-RPC 标准调用。
- **事件流转**：验证了从 Flow 内部发射细粒度事件，到 SSE 端点正确接收的全链路。

```text
============================================================
✅ 所有 19 个测试通过！
============================================================
```

## 4. 下一步规划
随着三协议适配层和流式进度系统的就绪，`AgenticX-DeepResearch` 已经具备了成为 NEAR AI 生态中“明星级”数字分身的基础。

下一步，我们建议：
1. **开发前端交互面板**：基于 React/Vue 开发一个轻量级的可视化面板，直接对接我们的 SSE 接口，展示极具科技感的“思考过程”UI。
2. **部署与上链**：将本服务部署到云端，并在 NEAR AI Agent Market 上进行正式注册，验证真实的跨链 A2A 互操作。

---
**References:**
[1] Google A2A Standard (2025). "Agent-to-Agent Protocol Specification."
[2] Anthropic MCP (2024). "Model Context Protocol."
