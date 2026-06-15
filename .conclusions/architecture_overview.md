# AgenticX-DeepResearch 架构与产物概览

**作者：** Damon Li (由 Manus AI 梳理)
**日期：** 2026-06-15

本文档旨在为 AI Coding 工具（如 Cursor、Windsurf、Copilot 等）和新加入的开发者提供项目的全局视角。通过阅读本文档，AI 工具可以快速建立对代码库的上下文理解，而无需扫描全量代码。

## 1. 项目定位
`AgenticX-DeepResearch` 是一个基于 `AgenticX` (agx) 框架构建的**深度调研智能体**。它能够针对复杂主题进行多轮迭代搜索、自适应规划、内容分析，并最终生成包含知识图谱和引用的深度研究报告。

该项目已完成 6 个阶段的重构，目前不仅是一个本地 CLI 工具，更是一个支持 A2A (Agent-to-Agent) 和 MCP (Model Context Protocol) 协议的标准化 AI 服务，可直接挂载到 NEAR AI Agent Market 和 IronClaw 等生态中。

## 2. 核心架构设计

项目采用高度模块化的设计，主要分为以下几个层次：

- **服务层 (Server)**: 提供 FastAPI 接口、SSE 实时流、以及 A2A / MCP 协议适配。
- **工作流层 (Flows & Workflows)**: 基于 `agenticx.flow` 构建的声明式状态机，控制调研的生命周期。
- **智能体层 (Agents)**: 负责具体任务的 ReAct 架构智能体（如查询生成、搜索分析、报告撰写）。
- **工具层 (Tools)**: 封装了各类搜索引擎和多模态文档解析能力。
- **数据与模型层 (Models & DB)**: 统一的 Pydantic 数据模型和 SQLite 持久化存储。

## 3. 核心产物清单

项目的产物（Deliverables）主要包括以下几类：

1. **结构化研究报告**: 默认输出到 `output/` 目录，包含主报告和多个子报告（执行摘要、详细分析、方法论等）。
2. **知识图谱 (Knowledge Graph)**: 调研过程中提取的事实、概念和关系，以 GraphRAG 格式沉淀。
3. **SSE 进度流**: 细粒度的执行事件（如搜索开始、总结完成），供前端 UI 渲染实时进度。
4. **Agent Card**: `/.well-known/agent.json`，用于在 A2A 网络中声明自身能力。
5. **MCP Tools**: 暴露给宿主框架（如 IronClaw）的 RPC 工具集。

## 4. 目录结构说明

```text
.
├── .conclusions/        # AI Coding 工具上下文摘要目录
├── agents/              # ReAct 智能体定义 (查询生成、总结、分析、报告撰写)
├── db/                  # SQLite 数据库模型与管理器
├── flows/               # 基于 agenticx.flow 的核心工作流引擎 (Basic & Advanced)
├── interactive/         # CLI 交互与实时监控界面
├── report/              # 报告构建器与质量评估模块
├── server/              # FastAPI 服务、SSE 推送、A2A/MCP 协议适配层
├── tools/               # 搜索引擎接入 (BochaAI/Bing/Google) 与多模态解析
├── workflows/           # 遗留的统一工作流 (逐步被 flows/ 取代)
├── models.py            # 全局 Pydantic 数据模型
├── main.py              # CLI 启动入口
├── config.yaml          # 全局配置文件
├── DEPLOYMENT.md        # 云端部署与 NEAR AI 注册指南
└── Dockerfile           # 容器化部署配置
```

在接下来的文件中，我们将对每个核心模块进行详细的代码摘要。
