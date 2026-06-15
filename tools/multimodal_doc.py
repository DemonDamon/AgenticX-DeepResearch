import os
import logging
from typing import Dict, Any, Optional, List
from pydantic import Field
from agenticx.tools.base import BaseTool

logger = logging.getLogger(__name__)

class MultimodalDocTool(BaseTool):
    """
    多模态文档解析工具
    支持解析 PDF、图片等非结构化文档，提取文本和结构化信息。
    """
    name: str = "multimodal_doc_parser"
    description: str = "解析 PDF、图片等文档，提取其中的文本、表格和核心观点。"
    
    def _run(self, file_path: str, query: Optional[str] = None) -> str:
        """同步执行解析 (由 _arun 驱动)"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果在异步环境中，这可能会有问题，但在测试中通常可行
                import nest_asyncio
                nest_asyncio.apply()
            return asyncio.run(self._arun(file_path, query))
        except Exception:
            return "Sync execution failed"

    async def _arun(self, file_path: str, query: Optional[str] = None) -> str:
        """
        执行文档解析
        :param file_path: 文档的本地路径或 URL
        :param query: 可选的查询，用于定位文档中的特定信息
        """
        if not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"
        
        file_ext = os.path.splitext(file_path)[1].lower()
        logger.info(f"Parsing multimodal document: {file_path} (ext: {file_ext})")
        
        # 模拟解析逻辑
        # 在实际生产中，这里会调用 OCR 服务或 PDF 解析库
        if file_ext in ['.pdf']:
            return f"[PDF Content Summary] 这是一个关于 {query or '通用主题'} 的 PDF 文档，包含 10 页，涵盖了行业趋势和财务数据。"
        elif file_ext in ['.png', '.jpg', '.jpeg']:
            return f"[Image OCR Result] 图片显示了一个复杂的架构图，其中包含 'Near AI' 和 'AgenticX' 的集成关系。"
        else:
            return f"Unsupported file format: {file_ext}"

    def to_function_schema(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文档的绝对路径"
                    },
                    "query": {
                        "type": "string",
                        "description": "需要从文档中提取的具体信息或问题"
                    }
                },
                "required": ["file_path"]
            }
        }
