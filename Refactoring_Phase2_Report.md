# AgenticX-DeepResearch 第二阶段重构报告：智能体与工作流重塑

本阶段完成了从硬编码逻辑向**声明式、可规划、异步化**现代架构的全面跃迁。

## 1. 核心变更概览

| 维度 | 旧架构 (Phase 1) | 新架构 (Phase 2) | 核心收益 |
| :--- | :--- | :--- | :--- |
| **Agent 基类** | 自定义异步包装 | **ReActAgent (Async)** | 支持原生 Function Calling、流式事件、自动重试 |
| **工作流控制** | 硬编码循环 (`unified_research_workflow.py`) | **agenticx.flow (声明式)** | 解耦业务逻辑，支持可视化、断点续传和复杂路由 |
| **规划机制** | 简单的“知识空白”检测 | **AdaptivePlanner + ExecutionPlan** | 实现真正的“边执行边规划”，支持动态任务增删 |
| **执行模式** | 顺序执行 | **异步并发 (Asyncio)** | 大幅提升搜索和处理吞吐量 |

## 2. 详细重构内容

### 2.1 Agent 升级
- **QueryGeneratorAgent**: 迁移至 `ReActAgent`。将查询生成逻辑封装为 `QueryGenerationTool`，允许 Agent 自主决定是否需要补充更多查询。
- **ResearchSummarizerAgent**: 迁移至 `ReActAgent`。直接注入搜索工具，Agent 现在可以自主决定“搜索-阅读-反思”的循环次数，而非被动接受指令。
- **ReportWriterAgent**: 适配异步接口，支持分章节并行撰写。

### 2.2 声明式 Flow 引擎集成
- **BasicResearchFlow**: 实现了 `@start` -> `@listen` 的线性流。
  - `generate_initial_queries` -> `search_and_summarize` -> `write_report`
- **AdvancedResearchFlow**: 实现了带条件路由的复杂流。
  - 使用 `@router` 装饰器实现动态决策：根据 `completeness_score` 和 `ExecutionPlan` 状态决定是 `continue_search` 还是 `finalize_report`。

### 2.3 智能重规划 (AdaptivePlanner)
- 引入了 `ExecutionPlan` 作为全局进度表。
- 在每一轮迭代后，调用 `AdaptivePlanner.propose_plan_patch`。
- 如果 Agent 在搜索中发现新领域，Planner 会生成 `PlanPatch` 动态修改后续的 `ExecutionStage` 和 `Subtask`，实现调研深度的自动扩展。

## 3. 测试验证
- **集成测试套件**: `tests/test_flow_v2.py`
- **覆盖范围**: 
  - [x] BasicFlow 线性流转验证
  - [x] AdvancedFlow 路由与循环验证
  - [x] Planner 计划修补应用验证
  - [x] Mock 模式下的全链路闭环
- **结果**: 两个核心工作流均已通过 100% 自动化测试。

## 4. 后续规划 (Phase 3)
- **长程记忆与知识库**: 接入 `agenticx.knowledge` 的 GraphRAG，实现跨任务的知识沉淀。
- **人类干预 (HITL)**: 利用 `ExecutionPlan` 的暂停/恢复机制，在关键规划节点引入人类反馈。
- **数字分身封装**: 针对 Near 协议进行接口适配。
