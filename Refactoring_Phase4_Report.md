## AgenticX-DeepResearch 第四阶段重构报告：服务化与协议适配

**日期：** 2026年6月15日
**作者：** Manus AI

### 1. 概述

本报告详细记录了 `AgenticX-DeepResearch` 项目第四阶段的重构工作，即“服务化与协议适配”。此阶段的核心目标是将原有的本地命令行工具转化为一个可被外部系统（如 Near AI 或自定义前端）通过 API 调用的、具备流式进度输出能力的深度调研 Agent 服务。通过引入 FastAPI、Server-Sent Events (SSE) 和 SQLite 数据库，我们成功构建了一个具备任务提交、实时进度追踪和历史记录持久化能力的服务端架构，并为未来与 Near AI 生态的集成奠定了基础。

### 2. 核心成果

#### 2.1 FastAPI 服务架构

*   **API 接口**：引入 FastAPI 框架，构建了 `/api/research/task` 接口用于提交新的调研任务，以及 `/api/research/task/{task_id}` 接口用于查询任务状态。所有任务均以异步方式在后台执行，并返回 `task_id` 供客户端追踪。
*   **异步任务管理**：通过 FastAPI 的 `BackgroundTasks` 机制，确保调研 Flow 在独立的后台线程中运行，不阻塞主 API 进程，从而实现高并发处理能力。
*   **依赖注入**：LLM 提供方和搜索工具等核心组件通过依赖注入的方式在 `run_research_task` 中动态初始化，保持了模块的解耦和可配置性。

#### 2.2 SSE (Server-Sent Events) 流式进度推送

*   **实时反馈**：实现了 `/api/research/task/{task_id}/events` SSE 接口，允许客户端订阅特定任务的实时进度更新。调研 Flow 在执行过程中的关键步骤（如“正在初始化”、“正在搜索”、“报告生成完成”）都会作为事件通过 SSE 推送给客户端。
*   **事件持久化**：SSE 事件不再是瞬时内存数据，而是通过数据库持久化，确保客户端即使在断开重连后也能获取到完整的历史事件流。

#### 2.3 任务状态持久化 (SQLite)

*   **数据库集成**：引入 SQLAlchemy ORM 和 SQLite 数据库，实现了调研任务状态的持久化存储。`db/models.py` 定义了 `ResearchTask` 模型，用于存储任务 ID、主题、目标、模式、状态、结果、错误信息、创建/完成时间以及所有历史事件。
*   **统一管理**：`db/manager.py` 提供了统一的数据库操作接口（`create_task`, `update_task_status`, `add_event`, `get_task`, `list_tasks`），简化了 API 层与数据库的交互。
*   **数据完整性**：确保了在服务重启或崩溃后，所有已提交任务的状态和进度信息不会丢失，为长程任务管理提供了基础。

#### 2.4 Near AI 协议适配框架

*   **抽象适配层**：初步设计并实现了 `server/near_adapter.py`，定义了 `NearAgentMessage` 消息格式和 `NearAdapter` 类。该适配层旨在封装 Near AI Agent-to-Agent (A2A) 协议的通信逻辑。
*   **元数据定义**：`NearAdapter` 提供了 `get_agent_card` 方法，用于生成 Agent 的元数据（如名称、描述、能力、Near 账户和费用结构），以便在 Near Agent Marketplace 中注册和展示。
*   **未来扩展**：该适配层为后续与 Near AI Agent SDK 的实际对接预留了接口，包括处理来自 Near 网络的请求 (`handle_request`)，以及集成 TEE (Trusted Execution Environment) 证明等 Near 平台特有的安全机制。

### 3. 集成测试与验证

*   **测试套件**：编写了 `tests/test_server_v1.py` 集成测试脚本，全面验证了 FastAPI 接口、SSE 流式推送和数据库持久化的协同工作。
*   **测试覆盖**：测试用例涵盖了健康检查、任务创建、任务状态查询以及 SSE 事件流的接收。通过 Mock `run_research_task`，确保了在不实际运行完整 Flow 的情况下，服务层逻辑的正确性。
*   **结果**：所有测试用例均已通过，验证了服务化改造的稳健性。

### 4. 结论与展望

第四阶段的重构工作成功地将 `AgenticX-DeepResearch` 从一个本地运行的 Agent 引擎，提升为一个具备 API 接口、实时进度反馈和任务持久化能力的服务。这为将其部署到云端、集成到 Web 应用或对接更复杂的 Agent 生态系统（如 Near AI）奠定了坚实的基础。

**下一步展望：**

*   **Near AI SDK 深度集成**：根据 Near AI Agent SDK 的具体规范，完善 `NearAdapter`，实现真正的 A2A 通信和 Agent 注册。
*   **Flow 事件钩子**：优化 Flow 引擎，使其能够更细粒度地发射事件，从而提供更丰富的 SSE 进度信息。
*   **前端 UI 构建**：开发一个简单的 Web UI，模拟 Kimi 的“深度研究”界面，直观展示 Agent 服务的调用和 SSE 进度流。

通过这些持续的演进，`AgenticX-DeepResearch` 将成为一个功能强大、易于集成且具备未来扩展潜力的深度调研智能体平台。

---

**References**

1.  [FastAPI Documentation](https://fastapi.tiangolo.com/)
2.  [Server-Sent Events (SSE) - MDN Web Docs](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
3.  [SQLAlchemy Documentation](https://docs.sqlalchemy.org/en/20/)
4.  [NEAR AI Official Website](https://near.ai/)
5.  [AgenticX GitHub Repository](https://github.com/DemonDamon/AgenticX)
