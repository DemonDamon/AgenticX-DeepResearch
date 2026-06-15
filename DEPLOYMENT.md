# AgenticX-DeepResearch 云端部署与 NEAR AI Agent Market 注册指南

**作者：** Manus AI  
**日期：** 2026-06-15  
**适用版本：** v0.5.0（Phase 6 重构完成后）

---

本指南详细介绍了如何将 `AgenticX-DeepResearch` 服务（基于 FastAPI 和三协议适配层）从本地开发环境打包、部署到云端（以 [Railway](https://railway.com/) 为主要示例），并将其作为 Service Provider 正式注册到 **NEAR AI Agent Market**，使其成为 NEAR 生态中可被其他 Agent（如 IronClaw）发现、调用并获得 NEAR Token 报酬的独立服务。

---

## 目录

1. [整体架构概览](#1-整体架构概览)
2. [前置条件](#2-前置条件)
3. [本地 Docker 打包与测试](#3-本地-docker-打包与测试)
4. [Railway 云端部署](#4-railway-云端部署)
5. [Render 云端部署（备选方案）](#5-render-云端部署备选方案)
6. [NEAR AI Agent Market 注册](#6-near-ai-agent-market-注册)
7. [IronClaw MCP 接入验证](#7-ironclaw-mcp-接入验证)
8. [A2A 协议发现端点说明](#8-a2a-协议发现端点说明)
9. [故障排查](#9-故障排查)

---

## 1. 整体架构概览

部署完成后，服务的调用链路如下所示：

```
用户 / 其他 Agent
      │
      ▼
NEAR AI Agent Market (market.near.ai)
      │  通过 Marketplace 代理路由
      ▼
AgenticX-DeepResearch FastAPI 服务
      │  (部署在 Railway / Render 等云平台)
      ├── /protocols/mcp/invoke         ← MCP 工具调用端点（IronClaw 接入）
      ├── /protocols/a2a/tasks/send     ← A2A 任务委托端点
      ├── /.well-known/agent.json       ← A2A Agent Card 发现端点
      ├── /api/research/task/{id}/sse   ← SSE 实时进度流
      └── /api/research/task/{id}/report ← 最终报告获取
            │
            ▼
      AgenticX Flow 引擎
      ├── BasicResearchFlow / AdvancedResearchFlow
      ├── AdaptivePlanner（动态重规划）
      ├── Multi-Brain 协同架构
      └── KnowledgeGraphBuilder（结果沉淀）
```

---

## 2. 前置条件

在开始之前，请确保你已准备好以下内容：

| 条件 | 说明 |
| :--- | :--- |
| GitHub 账号 | 代码仓库已推送至 `https://github.com/DemonDamon/AgenticX-DeepResearch` |
| Railway 账号 | 注册地址：https://railway.app/ |
| Kimi API Key | 默认 LLM 提供商，申请地址：https://platform.moonshot.cn/ |
| BochaAI API Key | 默认搜索引擎，申请地址：https://bochaai.com/ |
| NEAR 钱包 | 用于 NEAR AI Market 注册，创建地址：https://wallet.near.org |
| Docker（本地测试可选） | 安装地址：https://docs.docker.com/get-docker/ |

---

## 3. 本地 Docker 打包与测试

在推送到云端之前，建议先在本地用 Docker 验证服务能否正常启动。项目根目录已包含 `Dockerfile` 和 `docker-compose.yml`。

### 3.1 配置环境变量

复制环境变量模板并填写你的 API Key：

```bash
cp env_template.txt .env
# 编辑 .env，填写以下关键变量：
# KIMI_API_KEY=your_kimi_api_key
# BOCHAAI_API_KEY=your_bochaai_api_key
```

### 3.2 使用 Docker Compose 启动

```bash
# 构建并启动服务（后台运行）
docker compose up -d --build

# 查看启动日志
docker compose logs -f agenticx-deepresearch
```

### 3.3 验证服务健康状态

```bash
# 检查健康端点
curl http://localhost:8000/health

# 访问 API 文档（Swagger UI）
open http://localhost:8000/docs

# 验证 A2A Agent Card 端点（路由前缀为 /protocols）
curl http://localhost:8000/protocols/.well-known/agent.json

# 验证 MCP 工具列表端点
curl http://localhost:8000/protocols/mcp/tools

# 通过 MCP JSON-RPC 调用深度调研工具
curl -X POST http://localhost:8000/protocols/mcp/call \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "deep_research", "arguments": {"topic": "test"}}}'
```

如果 `/protocols/.well-known/agent.json` 返回了包含 `deep_research` 技能的 JSON，说明服务已就绪。

---

## 4. Railway 云端部署

Railway 是目前最适合快速部署 Python FastAPI 服务的云平台之一，支持从 GitHub 仓库自动检测 Dockerfile 并一键部署 [1]。

### 4.1 推送 Dockerfile 到 GitHub

确保以下文件已提交到 GitHub 仓库：

```bash
git add Dockerfile railway.json docker-compose.yml SKILL.md service-registration.json
git commit -m "feat: add deployment configuration files"
git push origin main
```

### 4.2 在 Railway 上创建项目

1. 登录 [Railway 控制台](https://railway.app/)，点击 **New Project**。
2. 选择 **Deploy from GitHub repo**，授权并选择 `AgenticX-DeepResearch` 仓库。
3. Railway 会自动检测到根目录的 `Dockerfile`，点击 **Deploy Now**。

### 4.3 配置环境变量

部署启动后，进入 Railway 项目的 **Variables** 选项卡，添加以下环境变量：

| 变量名 | 值 |
| :--- | :--- |
| `KIMI_API_KEY` | 你的 Kimi API Key |
| `KIMI_API_BASE` | `https://api.moonshot.cn/v1`（可选，有默认值）|
| `BOCHAAI_API_KEY` | 你的 BochaAI API Key |
| `DATABASE_URL` | `sqlite:///./research.db`（默认值，无需修改）|

### 4.4 获取公网域名

进入 **Settings** -> **Networking** 选项卡，点击 **Generate Domain**，Railway 将生成一个公网 HTTPS URL，例如：

```
https://agenticx-deepresearch-production.up.railway.app
```

**重要：** 记录此 URL，后续注册 NEAR AI Market 时需要用到。

### 4.5 验证云端部署

```bash
export DEPLOY_URL="https://agenticx-deepresearch-production.up.railway.app"

# 验证服务在线
curl $DEPLOY_URL/health

# 验证 A2A Agent Card（NEAR AI Market 注册的关键端点）
curl $DEPLOY_URL/.well-known/agent.json

# 提交一个测试调研任务
curl -X POST $DEPLOY_URL/api/research/start \
  -H "Content-Type: application/json" \
  -d '{"topic": "test: NEAR AI 2026 development", "mode": "basic"}'
```

---

## 5. Render 云端部署（备选方案）

如果你更倾向于使用 [Render](https://render.com/)，步骤如下 [2]：

1. 登录 Render，点击 **New** -> **Web Service**。
2. 连接你的 GitHub 仓库，选择 `AgenticX-DeepResearch`。
3. Render 会自动检测 `Dockerfile`。在 **Environment** 选项卡中添加与 Railway 相同的环境变量。
4. 点击 **Create Web Service**，等待构建完成。
5. Render 同样会提供一个公网 HTTPS URL。

Render 免费层有冷启动问题（服务闲置 15 分钟后会休眠），建议对于生产环境使用付费计划。

---

## 6. NEAR AI Agent Market 注册

NEAR AI Agent Market 是一个去中心化的 AI Agent 交易市场，Agent 可以在其中发布服务、接受任务并以 NEAR Token 结算 [3]。通过我们在 Phase 6 实现的 `NearAdapter`（`server/near_adapter.py`），你的服务已具备接入所需的全部协议端点。

### 6.1 注册 Agent 身份

向 NEAR AI Market API 发送注册请求，获取 `agent_api_key`：

```bash
curl -X POST https://market.near.ai/v1/agents/register \
  -H "Content-Type: application/json" \
  -d '{
    "handle": "agenticx_researcher",
    "description": "AgenticX Deep Research Agent - Multi-brain adaptive research framework powered by AgenticX",
    "capabilities": {
      "skills": ["deep_research", "report_generation", "knowledge_graph"]
    },
    "tags": ["research", "analysis", "agenticx", "mcp", "a2a"]
  }'
```

将返回的 `agent_api_key` 保存为环境变量：

```bash
export AGENT_API_KEY="your_returned_agent_api_key"
```

### 6.2 更新 service-registration.json

将 `service-registration.json` 中的 `endpoint_url` 替换为你的实际部署域名：

```bash
# 将 YOUR_DEPLOYMENT_DOMAIN 替换为实际域名
sed -i 's|YOUR_DEPLOYMENT_DOMAIN|agenticx-deepresearch-production.up.railway.app|g' service-registration.json
```

或直接编辑文件，确保 `endpoint_url` 指向 MCP 调用端点：

```json
{
  "name": "AgenticX Deep Research Service",
  "description": "Premium deep research agent powered by AgenticX...",
  "category": "research",
  "pricing_model": "per_call",
  "price_amount": "0.5",
  "endpoint_url": "https://agenticx-deepresearch-production.up.railway.app/protocols/mcp/call",
  "tags": ["research", "analysis", "deep-dive", "report", "knowledge-graph", "mcp"],
  "enabled": true,
  "response_time_seconds": 600,
  "settlement_interval": 10
}
```

### 6.3 发布 Service 到市场

```bash
curl -X POST https://market.near.ai/v1/agents/me/services \
  -H "Authorization: Bearer $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d @service-registration.json
```

保存返回的 `service_id`：

```bash
export SERVICE_ID="your_returned_service_id"
```

### 6.4 验证 Service 上线

```bash
# 查询服务状态
curl https://market.near.ai/v1/agents/me/services/$SERVICE_ID \
  -H "Authorization: Bearer $AGENT_API_KEY"

# 通过 Marketplace 代理发起测试调用
curl -X POST https://market.near.ai/v1/services/$SERVICE_ID/invoke \
  -H "Authorization: Bearer $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": {"query": "测试调研：NEAR AI 2026 年最新进展"}}'
```

如果返回包含 `task_id` 的 JSON 响应，说明你的 AgenticX-DeepResearch 已成功接入 NEAR AI 生态！

### 6.5 推广你的 Agent

将你的 `service_id` 和 `SKILL.md` 文件链接分享到 [NEAR AI Market Telegram 社区](https://t.me/nearaimarket)，让其他开发者和 Agent 发现并使用你的深度调研服务。

---

## 7. IronClaw MCP 接入验证

[IronClaw](https://github.com/nearai/ironclaw) 是 NEAR AI 的开源 Agent OS，支持通过 MCP 协议直接调用外部工具 [4]。你可以将 AgenticX-DeepResearch 配置为 IronClaw 的一个 MCP Server，让 IronClaw 直接调用你的深度调研能力。

### 7.1 在 IronClaw 中配置 MCP Server

在 IronClaw 的 `config.toml` 中添加以下配置（将 URL 替换为你的实际部署域名）：

```toml
[[mcp.servers]]
name = "agenticx-deep-research"
url = "https://agenticx-deepresearch-production.up.railway.app/protocols/mcp"
transport = "http"
```

### 7.2 验证 MCP 工具发现

IronClaw 启动后，可以通过以下命令验证工具是否被正确发现：

```bash
# 直接调用 MCP 工具列表端点
curl -X POST https://agenticx-deepresearch-production.up.railway.app/protocols/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}'
```

预期返回包含三个工具：`deep_research`、`get_research_status`、`get_research_report`。

### 7.3 通过 IronClaw 触发调研

在 IronClaw 的对话界面中，你可以直接说：

> "请帮我深度调研 2026 年 NEAR AI 生态的发展现状，使用 AgenticX 调研工具。"

IronClaw 会自动调用 `deep_research` 工具，并将结果返回给你。

---

## 8. A2A 协议发现端点说明

我们的服务实现了 [Google A2A 开放标准](https://google.github.io/A2A/)，任何支持 A2A 协议的 Agent 都可以通过标准的 `/.well-known/agent.json` 端点发现并委托任务给你的 Agent [5]。

### 8.1 Agent Card 端点

```
GET https://your-deployment-domain.com/.well-known/agent.json
```

该端点返回的 Agent Card 包含以下关键信息：

- **名称与描述**：Agent 的身份信息
- **技能列表**：`deep_research`（深度调研）和 `knowledge_graph_export`（知识图谱导出）
- **能力声明**：支持流式输出、推送通知、多模态输入
- **认证方式**：Bearer Token

### 8.2 A2A 任务委托端点

```
POST https://your-deployment-domain.com/protocols/a2a/tasks/send
```

任何支持 A2A 协议的 Agent（如 Claude、Gemini Agent）都可以通过此端点直接委托调研任务，无需经过 NEAR AI Market。

---

## 9. 故障排查

| 问题 | 可能原因 | 解决方案 |
| :--- | :--- | :--- |
| Railway 构建失败 | `requirements.txt` 中有本地路径依赖 | 确保 `AgenticX` 框架已发布到 PyPI，或在 Dockerfile 中单独复制安装 |
| `/health` 返回 500 | 数据库初始化失败 | 检查 `DATABASE_URL` 环境变量，确保 SQLite 文件路径有写权限 |
| `/.well-known/agent.json` 返回 404 | `NearAdapter` 路由未注册 | 检查 `server/api.py` 是否已 `include_router(near_adapter.router)` |
| MCP `tools/list` 返回空列表 | MCP 端点路由配置错误 | 检查 `server/near_adapter.py` 中 MCP 路由的 `prefix` 配置 |
| NEAR Market 注册返回 401 | `agent_api_key` 无效或过期 | 重新执行步骤 6.1 注册新的 API Key |
| 调研任务超时 | LLM API Key 无效或搜索 API 限流 | 检查 `KIMI_API_KEY` 和 `BOCHAAI_API_KEY` 是否正确配置 |

---

## References

[1] Deploy a FastAPI App | Railway Guides. https://docs.railway.com/guides/fastapi

[2] Deploy a FastAPI App – Render Docs. https://render.com/docs/deploy-fastapi

[3] Introducing NEAR AI Agent Market. https://near.ai/blog/introducing-near-ai-agent-market

[4] IronClaw is an Agent OS focused on privacy, security and extensibility. https://github.com/nearai/ironclaw

[5] Agent Discovery, Naming, and Resolution - the Missing Pieces to A2A. https://www.solo.io/blog/agent-discovery-naming-and-resolution---the-missing-pieces-to-a2a

[6] Twelve Data Service for NEAR AI Agent Market (参考注册格式). https://github.com/twelvedata/near-ai-agent-market

[7] SKILL.md is quietly becoming the standard for teaching AI agents. https://www.reddit.com/r/AI_Agents/comments/1stcu8e/skillmd_is_quietly_becoming_the_standard_for/
