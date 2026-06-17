#!/usr/bin/env python3
"""
AgenticX 深度搜索系统 (v2)
基于 agenticx.flow 和 ReActAgent 的全新重构版本。
"""

import argparse
import asyncio
import logging
import os
import sys
import yaml
import warnings
from typing import AsyncGenerator, Dict, Any, Generator, List, Optional, Union
from pathlib import Path

from pydantic import Field

# 过滤弃用警告
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich import box
except ImportError:
    Console = Panel = Text = Table = Progress = SpinnerColumn = TextColumn = box = None

# 导入核心组件
from agenticx.llms import OpenAIProvider
from agenticx.llms.base import BaseLLMProvider
from agenticx.llms.kimi_provider import KimiProvider
from agenticx.llms.response import LLMChoice, LLMResponse, TokenUsage
from tools import BochaaISearchTool, BingSearchTool, GoogleSearchTool
from flows import BasicResearchFlow, AdvancedResearchFlow, ResearchState
from utils import clean_input_text

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

console = Console() if Console else None


class OpenAICompatibleProvider(BaseLLMProvider):
    """Minimal OpenAI-compatible provider for custom base URLs."""

    api_key: str
    base_url: Optional[str] = None
    timeout: Optional[float] = 300.0
    max_retries: Optional[int] = 3
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 8192
    client: Optional[Any] = Field(default=None, exclude=True)
    async_client: Optional[Any] = Field(default=None, exclude=True)

    def __init__(self, **data):
        super().__init__(**data)
        from openai import AsyncOpenAI, OpenAI

        client_kwargs = {
            "api_key": self.api_key,
            "timeout": self.timeout,
            "max_retries": self.max_retries or 3,
        }
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        object.__setattr__(self, "client", OpenAI(**client_kwargs))
        object.__setattr__(self, "async_client", AsyncOpenAI(**client_kwargs))

    def _messages(self, prompt: Union[str, List[Dict]]) -> List[Dict]:
        if isinstance(prompt, str):
            return [{"role": "user", "content": prompt}]
        return prompt

    def _to_response(self, response: Any) -> LLMResponse:
        choice = response.choices[0] if response.choices else None
        message = choice.message if choice else None
        content = (message.content if message else "") or ""
        usage = response.usage
        tool_calls = None
        if message and getattr(message, "tool_calls", None):
            tool_calls = [
                tool_call.model_dump(exclude_none=True)
                for tool_call in message.tool_calls
            ]
        return LLMResponse(
            id=getattr(response, "id", ""),
            model_name=getattr(response, "model", self.model),
            created=getattr(response, "created", 0) or 0,
            content=content,
            choices=[
                LLMChoice(
                    index=getattr(choice, "index", 0) if choice else 0,
                    content=content,
                    finish_reason=getattr(choice, "finish_reason", None) if choice else None,
                )
            ],
            token_usage=TokenUsage(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
                total_tokens=getattr(usage, "total_tokens", 0) if usage else 0,
            ),
            metadata={},
            tool_calls=tool_calls,
        )

    def _completion_kwargs(self, prompt: Union[str, List[Dict]], **kwargs: Any) -> Dict[str, Any]:
        call_kwargs = {
            "model": self.model,
            "messages": self._messages(prompt),
            "temperature": kwargs.pop("temperature", self.temperature),
            "max_tokens": kwargs.pop("max_tokens", self.max_tokens),
        }
        tools = kwargs.pop("tools", None)
        if tools:
            call_kwargs["tools"] = tools
        call_kwargs.update(kwargs)
        return {k: v for k, v in call_kwargs.items() if v is not None}

    def invoke(self, prompt: Union[str, List[Dict]], **kwargs: Any) -> LLMResponse:
        response = self.client.chat.completions.create(
            **self._completion_kwargs(prompt, **kwargs)
        )
        return self._to_response(response)

    async def ainvoke(self, prompt: Union[str, List[Dict]], **kwargs: Any) -> LLMResponse:
        response = await self.async_client.chat.completions.create(
            **self._completion_kwargs(prompt, **kwargs)
        )
        return self._to_response(response)

    def stream(self, prompt: Union[str, List[Dict]], **kwargs: Any) -> Generator[Union[str, Dict], None, None]:
        response = self.client.chat.completions.create(
            **self._completion_kwargs(prompt, stream=True, **kwargs)
        )
        for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            text = getattr(delta, "content", None) if delta else None
            if text:
                yield text

    async def astream(self, prompt: Union[str, List[Dict]], **kwargs: Any) -> AsyncGenerator[Union[str, Dict], None]:
        response = await self.async_client.chat.completions.create(
            **self._completion_kwargs(prompt, stream=True, **kwargs)
        )
        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            text = getattr(delta, "content", None) if delta else None
            if text:
                yield text

def print_info(message: str):
    if console:
        console.print(f"● {message}", style="white")
    else:
        print(f"● {message}")

def print_success(message: str):
    if console:
        console.print(f"● {message}", style="bright_green bold")
    else:
        print(f"● {message}")

def print_error(message: str):
    if console:
        console.print(f"● {message}", style="bright_red bold")
    else:
        print(f"● {message}")

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print_error(f"配置文件加载失败: {e}")
        return {}

def select_workflow_mode() -> str:
    print("\nSelect Research Workflow Mode:")
    print("1. Basic Mode - Direct deep search")
    print("2. Advanced Mode - Multi-round iteration (with Adaptive Planning)")
    
    while True:
        choice = input("\nSelect mode (1-2, default 1): ").strip()
        if choice in ('1', ''): return 'basic'
        if choice == '2': return 'advanced'
        print("Invalid choice, please select 1 or 2.")

def _get_provider_name(config: Dict[str, Any]) -> str:
    llm_config = config.get('llm', {})
    return os.getenv('LLM_PROVIDER') or llm_config.get('default_provider', 'kimi')

def _get_provider_config(config: Dict[str, Any]) -> Dict[str, Any]:
    llm_config = config.get('llm', {})
    provider_name = _get_provider_name(config)
    providers = llm_config.get('providers', {})
    provider_config = providers.get(provider_name, {})
    return provider_config or llm_config

def _get_search_config(config: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    search_config = config.get('search', {})
    engine = os.getenv('SEARCH_ENGINE') or search_config.get('default_engine') or search_config.get('engine', 'bochaai')
    engines = search_config.get('engines', {})
    return engine, engines.get(engine, {})

def _env_or_config(config_value: Any, env_name: Optional[str] = None) -> Optional[str]:
    if env_name and os.getenv(env_name):
        return os.getenv(env_name)
    if isinstance(config_value, str) and config_value:
        return config_value
    return None

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default

def _build_llm_provider(config: Dict[str, Any]):
    provider_name = _get_provider_name(config)
    llm_config = _get_provider_config(config)
    api_key_env = llm_config.get('api_key_env') or f"{provider_name.upper()}_API_KEY"
    base_url_env = llm_config.get('base_url_env') or f"{provider_name.upper()}_API_BASE"
    api_key = _env_or_config(llm_config.get('api_key'), api_key_env)
    base_url = (
        _env_or_config(llm_config.get('base_url'), base_url_env)
        or llm_config.get('base_url_default')
    )
    model_env = (
        os.getenv(f"{provider_name.upper()}_MODEL")
        or os.getenv(f"{provider_name.upper()}_MODEL_NAME")
    )
    model = model_env or llm_config.get('model')

    if not api_key:
        print_error(f"缺少 {api_key_env}，无法初始化 {provider_name} provider。")
        print_info("请检查 .env 或当前 shell 环境变量。")
        return None
    if not model:
        print_error(f"缺少 {provider_name} 模型名称，请在 config.yaml 或环境变量中配置。")
        return None

    common_kwargs = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "timeout": llm_config.get('timeout') or _env_float("LLM_TIMEOUT", 45.0),
        "max_retries": llm_config.get('max_retries'),
        "temperature": llm_config.get('temperature'),
        "max_tokens": llm_config.get('max_tokens'),
    }
    common_kwargs = {k: v for k, v in common_kwargs.items() if v is not None}

    if provider_name == 'kimi':
        common_kwargs.setdefault("base_url", "https://api.moonshot.cn/v1")
        return KimiProvider(**common_kwargs)

    if provider_name in {"openai", "cx_openai", "deepseek"}:
        return OpenAICompatibleProvider(**common_kwargs)

    if isinstance(model, str) and "/" not in model:
        common_kwargs["model"] = f"openai/{model}"
    return OpenAIProvider(**common_kwargs)

async def _run_flow_with_heartbeat(flow, topic: str, timeout: float):
    task = asyncio.create_task(flow.kickoff_async())
    elapsed = 0
    while not task.done():
        await asyncio.sleep(10)
        elapsed += 10
        print_info(f"仍在运行：{topic[:40]}... 已等待 {elapsed}s")
        if elapsed >= timeout:
            task.cancel()
            raise TimeoutError(f"研究执行超过 {int(timeout)} 秒，已取消。可通过 RUN_TIMEOUT 调整。")
    return await task

async def run_deep_search_async(topic: str, config: Dict[str, Any], workflow_mode: str = 'basic'):
    """异步运行深度搜索"""
    topic = clean_input_text(topic)
    if not topic:
        print_error("Invalid topic")
        return

    # 初始化 LLM
    llm = _build_llm_provider(config)
    if llm is None:
        return
    print_info(f"Using LLM provider: {_get_provider_name(config)} ({llm.model})")

    # 初始化搜索工具
    search_engine, search_config = _get_search_config(config)
    tools = []
    if search_engine == 'bochaai':
        api_key_env = search_config.get('api_key_env', 'BOCHAAI_API_KEY')
        tools.append(BochaaISearchTool(api_key=os.getenv(api_key_env)))
    elif search_engine == 'bing':
        api_key_env = search_config.get('api_key_env', 'BING_SUBSCRIPTION_KEY')
        tools.append(BingSearchTool(api_key=os.getenv(api_key_env) or os.getenv('BING_API_KEY')))
    else:
        api_key_env = search_config.get('api_key_env', 'GOOGLE_API_KEY')
        tools.append(GoogleSearchTool(api_key=os.getenv(api_key_env)))

    # 初始化 Flow 状态
    state = ResearchState(topic=topic, objective=f"对 {topic} 进行深度调研")

    # 选择并运行 Flow
    if workflow_mode == 'advanced':
        print_info(f"Starting Advanced Flow for: {topic}...")
        flow = AdvancedResearchFlow(llm_provider=llm, search_tools=tools, state=state)
    else:
        print_info(f"Starting Basic Flow for: {topic}...")
        flow = BasicResearchFlow(llm_provider=llm, search_tools=tools, state=state)

    try:
        run_timeout = _env_float("RUN_TIMEOUT", 120.0)
        report = await _run_flow_with_heartbeat(flow, topic, run_timeout)
        if not report:
            report = flow.state.final_report
        if not report:
            raise RuntimeError("研究流程没有生成报告，请检查模型权限、搜索 API Key 和上游错误日志。")
            
        print_success("\nResearch Completed!")
        print("\n" + "="*50 + "\n")
        print(report)
        print("\n" + "="*50 + "\n")
        
        # 保存报告
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        filename = output_dir / f"research_{topic.replace(' ', '_')}_{int(asyncio.get_event_loop().time())}.md"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        print_info(f"Report saved to: {filename}")

    except TimeoutError as e:
        print_error(str(e))
    except KeyboardInterrupt:
        print_error("用户已取消研究任务。")
    except Exception as e:
        print_error(f"Research failed: {e}")
        if os.getenv("DEBUG_TRACEBACK", "0") == "1":
            import traceback
            traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="AgenticX Deep Research v2")
    parser.add_argument("topic", nargs="?", help="Research topic")
    parser.add_argument("--mode", choices=['basic', 'advanced'], help="Workflow mode")
    args = parser.parse_args()

    config = load_config()
    
    topic = args.topic
    if not topic:
        print("\nWelcome to AgenticX Deep Research v2")
        topic = input("\nEnter research topic: ").strip()
    
    mode = args.mode or select_workflow_mode()
    
    asyncio.run(run_deep_search_async(topic, config, mode))

if __name__ == "__main__":
    main()
