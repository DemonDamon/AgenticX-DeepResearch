# AgenticX-DeepResearch 代码模块摘要

**作者：** Damon Li (由 Manus AI 梳理)
**日期：** 2026-06-15

本文档对 `AgenticX-DeepResearch` 项目的核心代码模块进行了详细梳理。AI Coding 工具可以读取此文件，快速理解各个类和函数的职责，避免解析成千上万行的源代码。

---

## 1. 智能体模块 (`agents/`)

该目录下的智能体均基于 `agenticx.core.agent.Agent`（ReAct 架构）进行重构，具备原生的工具调用和自我反思能力。它们协同工作，共同完成复杂的深度调研任务。

| 智能体类名 | 所在文件 | 核心职责与关键方法 |
| :--- | :--- | :--- |
| **QueryGeneratorAgent** | `query_generator.py` | 负责根据当前研究主题和上下文，动态生成高质量的搜索查询。核心方法为 `generate_queries()`，支持广泛探索、深度挖掘和空白填补等多种策略。 |
| **ResearchSummarizerAgent** | `research_summarizer.py` | 负责调用底层搜索工具获取数据，并对海量搜索结果进行初步提炼与总结。核心方法为 `execute_search_and_summarize()`。 |
| **SearchAnalyzerAgent** | `search_analyzer.py` | 负责深度分析已收集的搜索结果，精准识别知识空白（Knowledge Gap），并持续评估当前搜索策略的有效性。核心方法包括 `analyze_results()` 和 `identify_knowledge_gaps()`。 |
| **ReportWriterAgent** | `report_writer.py` | 负责将积累的研究上下文转化为结构化输出，包括生成大纲和撰写各章节内容。核心方法包括 `generate_report()`、`generate_outline()` 和 `write_section()`。 |
| **PlannerAgent** | `planner.py` | 旧版规划器实现，主要负责生成多步研究计划。在新版本架构中，其功能已逐渐被 `agenticx.planner.AdaptivePlanner` 替代。 |

---

## 2. 工作流模块 (`flows/`)

工作流模块是系统的核心大脑，完全基于 `agenticx.flow` 构建为声明式的状态机，用于精确控制调研的整个生命周期。

**ResearchState** 定义在 `basic_flow.py` 中，是贯穿整个工作流的全局状态对象。它承载了研究主题、上下文环境、系统配置、挂载的知识库以及事件发射器实例，确保各个执行节点之间的数据流转安全可靠。

**BasicResearchFlow** 实现了线性的基础研究工作流。其执行路径相对固定，依次经过初始查询生成（`generate_initial_queries`）、搜索执行（`execute_searches`）、结果分析（`analyze_results`）和报告撰写（`write_report`）等节点，适用于简单明确的调研任务。

**AdvancedResearchFlow** 定义在 `advanced_flow.py` 中，是一个带有条件路由的复杂工作流。它深度集成了动态重规划（AdaptivePlanner）和多脑协同架构。其核心节点不仅包括初始化和查询生成，还引入了自适应重规划节点（`adaptive_replanning`），系统会根据该节点的输出决定是继续深入搜索，还是直接进入报告撰写（`write_report`）与最终定稿（`finalize_report`）阶段。

---

## 3. 服务与协议适配模块 (`server/`)

服务模块负责将底层的深度研究能力封装并暴露为外部可调用的标准化网络服务。它不仅提供了传统的 REST API，还支持现代化的协议适配。

| 文件名 | 核心职责说明 |
| :--- | :--- |
| `api.py` | FastAPI 的主应用入口，定义了基础的 HTTP 路由。主要提供任务创建（`/api/research/start`）和状态查询（`/api/research/task/{id}/status`）等标准 REST 接口。 |
| `event_emitter.py` | 实现了细粒度的事件发射系统 `FlowEventEmitter`。它负责拦截工作流内部的每一个关键动作（例如查询生成、搜索完成），实时计算总体进度百分比，并将事件数据同时推送到内存队列和 SQLite 数据库中。 |
| `sse.py` | 实现了基于 Server-Sent Events 的流式推送端点。前端应用可以通过此接口建立长连接，实时监听并渲染由 `FlowEventEmitter` 产生的进度事件。 |
| `near_adapter.py` | 作为三协议统一适配层，极大地扩展了系统的互操作性。它实现了 A2A 协议（提供 `/.well-known/agent.json` 发现端点和任务委托端点）、MCP 协议（提供供 IronClaw 调用的工具发现与执行端点），以及基于异步回调的 NEAR Webhook。 |

---

## 4. 工具模块 (`tools/`)

工具模块中的所有类均继承自 `agenticx.tools.base.BaseTool`，为智能体提供了与外部世界交互的具体能力。

**BaseSearchTool** 位于 `base_search.py` 中，是所有搜索工具的统一基类。它强制规范了输入与输出的数据结构，定义了标准的 `SearchInput` 和 `SearchResponse` Pydantic 模型，确保上层智能体无需关心底层搜索引擎的差异。

基于上述基类，系统实现了 **BochaaIWebSearchTool**、**BingWebSearchTool** 和 **GoogleSearchTool** 等具体的搜索引擎接入类。其中，BochaAI 被配置为默认引擎，专门针对中文搜索场景进行了深度优化。

**MultimodalDocTool** 定义在 `multimodal_doc.py` 中，提供了多模态文档的解析能力。它支持读取本地文件路径或远程 URL，能够智能解析 PDF 文档和图片内容，并从中提取纯文本和核心观点供智能体分析。

---

## 5. 数据模型与持久化 (`models.py` & `db/`)

系统的数据模型被严格划分为业务逻辑层和持久化层。

全局的业务逻辑数据模型统一集中在根目录的 **`models.py`** 文件中。该文件完全基于 Pydantic 构建，定义了诸如 `SearchQuery`、`KnowledgeGap` 和 `ResearchContext` 等核心数据结构，保证了内存中数据流转的类型安全。

持久化层的数据模型则位于 **`db/models.py`** 中，使用 SQLAlchemy 定义。它包含了用于记录任务执行状态和历史事件的 `ResearchTask` 表，以及用于存储用户偏好的 `UserProfile` 表。同时，**`db/manager.py`** 实现了 `DBManager` 单例类，封装了所有针对 SQLite 数据库的底层 CRUD 操作。

---

## 6. 报告生成与质量评估 (`report/`)

报告生成模块负责将零散的研究发现整合为高质量的最终交付物。

**ReportBuilderTask** 位于 `report_builder.py` 中，负责将收集到的研究内容、知识图谱和数据结构化地组装为最终报告。它支持同时输出 Markdown 和 JSON 等多种格式，以满足不同场景的阅读和解析需求。

为了保证输出质量，系统引入了 **QualityAssessmentTask**（位于 `quality_assessment.py`）。该模块会对生成的报告进行严格的量化评估，评估维度涵盖内容的完整性、准确性、相关性、逻辑连贯性以及分析深度。

此外，**CitationManagerTask**（位于 `citation_manager.py`）专门负责管理报告中的所有参考文献。它会自动整理引用来源，确保最终报告中的每一项关键发现都有可靠的数据支撑并符合学术规范。

---

## 7. 交互模块 (`interactive/`)

交互模块主要包含 `RealTimeMonitor`、`ResearchInterface` 和 `UserFeedbackHandler` 等组件。

在纯 CLI 运行模式下，这些组件基于 Rich 库为开发者提供了美观的彩色终端输出、实时更新的进度条以及交互式的用户反馈机制。尽管在生产环境中，这些本地交互功能已主要被 FastAPI 提供的 Web 接口和 SSE 流式推送所替代，但该模块仍被完整保留，作为系统本地开发、调试和快速验证的重要工具。
