# ============================================================================
# AgenticX-DeepResearch Dockerfile
# 基于 Python 3.12 精简镜像，适用于 Railway / Render / Docker Compose 部署
# ============================================================================
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 Python 缓冲 stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 安装系统依赖（用于 PDF 解析等多模态工具）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建数据库和日志目录
RUN mkdir -p /app/output /app/logs

# 暴露 FastAPI 默认端口
EXPOSE 8000

# 启动命令（Railway 会自动注入 $PORT 环境变量）
CMD ["sh", "-c", "uvicorn server.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
