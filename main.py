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
from typing import Dict, Any, Optional
from pathlib import Path

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
from agenticx.llms.kimi_provider import KimiProvider
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

def _get_provider_config(config: Dict[str, Any]) -> Dict[str, Any]:
    llm_config = config.get('llm', {})
    provider_name = llm_config.get('default_provider', 'kimi')
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

async def run_deep_search_async(topic: str, config: Dict[str, Any], workflow_mode: str = 'basic'):
    """异步运行深度搜索"""
    topic = clean_input_text(topic)
    if not topic:
        print_error("Invalid topic")
        return

    # 初始化 LLM
    llm_config = _get_provider_config(config)
    api_key = _env_or_config(llm_config.get('api_key'), llm_config.get('api_key_env') or 'KIMI_API_KEY')
    base_url = (
        _env_or_config(llm_config.get('base_url'), llm_config.get('base_url_env') or 'KIMI_API_BASE')
        or llm_config.get('base_url_default')
        or 'https://api.moonshot.cn/v1'
    )
    if not api_key:
        print_error("缺少 KIMI_API_KEY，无法初始化 KimiProvider。")
        print_info("请先执行：cp env_template.txt .env，然后在 .env 中填写 KIMI_API_KEY。")
        print_info("如果只想临时运行，也可以执行：export KIMI_API_KEY='你的 key'")
        return

    llm = KimiProvider(
        api_key=api_key,
        base_url=base_url,
        model=os.getenv('KIMI_MODEL') or os.getenv('KIMI_MODEL_NAME') or llm_config.get('model', 'moonshot-v1-32k')
    )

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
        if console:
            with console.status(f"[bold green]Researching {topic}...", spinner="dots"):
                report = await flow.kickoff_async()
        else:
            report = await flow.kickoff_async()
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

    except Exception as e:
        print_error(f"Research failed: {e}")
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
