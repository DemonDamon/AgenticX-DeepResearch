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

async def run_deep_search_async(topic: str, config: Dict[str, Any], workflow_mode: str = 'basic'):
    """异步运行深度搜索"""
    topic = clean_input_text(topic)
    if not topic:
        print_error("Invalid topic")
        return

    # 初始化 LLM
    llm_config = config.get('llm', {})
    llm = KimiProvider(
        api_key=os.getenv('KIMI_API_KEY', llm_config.get('api_key')),
        base_url=os.getenv('KIMI_API_BASE', llm_config.get('base_url')),
        model=llm_config.get('model', 'moonshot-v1-32k')
    )

    # 初始化搜索工具
    search_engine = os.getenv('SEARCH_ENGINE', config.get('search', {}).get('engine', 'bochaai'))
    tools = []
    if search_engine == 'bochaai':
        tools.append(BochaaISearchTool(api_key=os.getenv('BOCHAAI_API_KEY')))
    elif search_engine == 'bing':
        tools.append(BingSearchTool(api_key=os.getenv('BING_API_KEY')))
    else:
        tools.append(GoogleSearchTool(api_key=os.getenv('GOOGLE_API_KEY')))

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
