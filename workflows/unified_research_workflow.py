"""
Unified Research Workflow Implementation (v2 - AGX Native)

基于 AgenticX 框架重构的统一深度研究工作流。
核心变更：
1. 全面异步化（async/await）
2. 使用新的 Agent/Tool 接口（ainvoke, SearchResponse）
3. 使用 Pydantic 数据模型（ResearchContext, SearchResult 等）
4. 保留三种模式：Basic / Interactive / Advanced
5. 保留向后兼容的同步 execute() 入口

Supports switching between modes via parameters.
"""

import json
import re
import yaml
import os
import time
import logging
import sys
import threading
import asyncio
import warnings
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from enum import Enum
from datetime import datetime


# 过滤弃用警告
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*There is no current event loop.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*datetime.datetime.utcnow.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="litellm.*")

from agenticx.core.workflow import Workflow
from agenticx.core.agent_executor import AgentExecutor
from agenticx.core.task import Task
from agenticx.llms.base import BaseLLMProvider
from agenticx.tools.base import BaseTool
from agenticx.observability.monitoring import MonitoringCallbackHandler
from agenticx.observability.logging import LoggingCallbackHandler

# Import local modules
current_dir = Path(__file__).parent.parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Import agents
from agents import QueryGeneratorAgent, ResearchSummarizerAgent, SearchAnalyzerAgent  # type: ignore

# Import search tools
from tools import (  # type: ignore
    GoogleSearchTool, BingWebSearchTool, MockBingSearchTool,
    BochaaIWebSearchTool, BaseSearchTool, SearchResponse, SearchResultItem
)

# Import utilities
from utils import clean_input_text  # type: ignore

# Import report components
from report import StructuredReportBuilderTask, CitationManagerTask, QualityAssessmentTask  # type: ignore

# Import models
from models import (  # type: ignore
    ResearchContext, ResearchIteration, SearchResult, Citation,
    SearchEngine, ResearchPhase, SearchQuery, KnowledgeGap, KnowledgeItem
)


class WorkflowMode(Enum):
    """Workflow execution modes"""
    BASIC = "basic"
    INTERACTIVE = "interactive"
    ADVANCED = "advanced"


class UnifiedResearchWorkflow:
    """
    Unified Research Workflow (v2 - AGX Native)
    
    基于 AgenticX 框架的深度研究工作流引擎。
    
    Supports three modes:
    1. Basic Mode: 多轮搜索循环 + 报告生成
    2. Interactive Mode: 反思 → 澄清 → 聚焦研究
    3. Advanced Mode: 多迭代自适应研究（含质量评估与策略调整）
    """
    
    def __init__(self, 
                 llm_provider: BaseLLMProvider, 
                 mode: WorkflowMode = WorkflowMode.BASIC,
                 max_research_loops: int = 3,
                 organization_id: str = "deepsearch", 
                 search_engine: str = "mock",
                 config_path: str = "config.yaml",
                 clarification_mode: str = "one_shot",
                 **kwargs):
        """
        Initialize unified research workflow
        
        Args:
            llm_provider: LLM provider (BaseLLMProvider)
            mode: Workflow mode (basic, interactive, advanced)
            max_research_loops: Maximum research loop count
            organization_id: Organization ID
            search_engine: Search engine type
            config_path: Configuration file path
            clarification_mode: "one_shot" or "progressive"
            **kwargs: Additional configuration parameters
        """
        self.llm_provider = llm_provider
        self.mode = mode
        self.max_research_loops = max_research_loops
        self.organization_id = organization_id
        self.config_path = config_path
        self.clarification_mode = clarification_mode
        self.language = "en"
        self.kwargs = kwargs
        
        # Initialize monitoring metrics
        self.metrics = {
            "execution_time": 0.0,
            "search_count": 0,
            "loop_count": 0,
            "success_rate": 0.0,
            "token_usage": 0,
            "error_count": 0,
            "clarification_count": 0,
            "thinking_steps": 0
        }
        
        # Initialize monitoring handlers
        self.monitoring_handler = MonitoringCallbackHandler()
        self.logging_handler = LoggingCallbackHandler(console_output=False)
        
        # Set up logging
        self._setup_logging()
        
        # Load configuration file
        self.config = self._load_config()
        
        # Initialize search tool
        self.search_tool: BaseSearchTool = self._initialize_search_tool(search_engine)
        
        # Initialize agents (新 AGX 接口)
        self.query_generator = QueryGeneratorAgent(
            name="QueryGenerator",
            role="Query Generation Expert",
            goal="Generate high-quality search queries to support deep research",
            organization_id=organization_id,
            llm_provider=llm_provider
        )
        self.search_analyzer = SearchAnalyzerAgent(
            name="SearchAnalyzer",
            role="Search Result Analyst",
            goal="Analyze search results, extract insights, identify knowledge gaps",
            organization_id=organization_id,
            llm_provider=llm_provider
        )
        self.research_summarizer = ResearchSummarizerAgent(
            organization_id=organization_id,
            llm_provider=llm_provider
        )
        
        # Initialize report building components
        self.report_builder = StructuredReportBuilderTask(
            description="Build comprehensive structured research reports",
            expected_output="Detailed multi-section research report with citations"
        )
        self.citation_manager = CitationManagerTask(
            description="Manage and format citations",
            expected_output="Properly formatted citation list"
        )
        self.quality_assessor = QualityAssessmentTask(
            description="Assess research and report quality",
            expected_output="Quality assessment report"
        )
        
        # Research context (Pydantic model)
        self.research_context: Dict[str, Any] = self._get_initial_research_context()
        
    # =========================================================================
    # Setup & Configuration
    # =========================================================================
    
    def _setup_logging(self):
        """Setup logging configuration"""
        log_filename = f"{self.mode.value}_research.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.FileHandler(log_filename)]
        )
        self.logger = logging.getLogger(__name__)
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration file"""
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    
    def _initialize_search_tool(self, search_engine: str) -> BaseSearchTool:
        """Dynamically initialize search tool"""
        try:
            if search_engine == "google":
                return self._create_google_search_tool()
            elif search_engine == "bing":
                return self._create_bing_search_tool()
            elif search_engine == "bochaai":
                return self._create_bochaai_search_tool()
            else:
                return self._create_mock_search_tool()
        except Exception:
            return self._create_mock_search_tool()
    
    def _create_google_search_tool(self) -> BaseSearchTool:
        """Create Google search tool"""
        google_config = self.config.get('google_search', {})
        api_key = google_config.get('api_key', '')
        if api_key and api_key.startswith('${') and api_key.endswith('}'):
            api_key = os.getenv(api_key[2:-1], '')
        if not api_key:
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("Google API Key not configured")
        return GoogleSearchTool(api_key=api_key)
    
    def _create_bing_search_tool(self) -> BaseSearchTool:
        """Create Bing search tool"""
        bing_config = self.config.get('bing_search', {})
        subscription_key = bing_config.get('subscription_key', '')
        if subscription_key and subscription_key.startswith('${') and subscription_key.endswith('}'):
            subscription_key = os.getenv(subscription_key[2:-1], '')
        if not subscription_key:
            subscription_key = os.getenv("BING_SUBSCRIPTION_KEY") or os.getenv("AZURE_SUBSCRIPTION_KEY", "")
        if not subscription_key:
            raise ValueError("Bing Subscription Key not configured")
        return BingWebSearchTool(subscription_key=subscription_key)
    
    def _create_bochaai_search_tool(self) -> BaseSearchTool:
        """Create BochaaI search tool"""
        bochaai_config = self.config.get('bochaai_search', {})
        api_key = bochaai_config.get('api_key', '')
        if api_key and api_key.startswith('${') and api_key.endswith('}'):
            api_key = os.getenv(api_key[2:-1], '')
        if not api_key:
            api_key = os.getenv("BOCHAAI_API_KEY", "")
        if not api_key:
            raise ValueError("BochaaI API Key not configured")
        return BochaaIWebSearchTool(api_key=api_key)
    
    def _create_mock_search_tool(self) -> BaseSearchTool:
        """Create mock search tool"""
        return MockBingSearchTool()
    
    def _get_initial_research_context(self) -> Dict[str, Any]:
        """Returns the initial structure for the research context."""
        return {
            "topic": "",
            "objective": "",
            "current_iteration": 0,
            "max_iterations": self.max_research_loops,
            "search_history": [],
            "findings": [],
            "knowledge_gaps": [],
            "thinking_process": [],
            "thinking_insights": [],
            "citations": [],
            "research_summaries": [],
            "original_topic": "",
            "clarified_topic": "",
            "research_focus": [],
            "search_results": [],
            "generated_queries": [],
            "errors": []
        }
    
    def reset_research_context(self):
        """Reset research context"""
        self.research_context = self._get_initial_research_context()
        self.metrics = {
            "execution_time": 0.0,
            "search_count": 0,
            "loop_count": 0,
            "success_rate": 0.0,
            "token_usage": 0,
            "error_count": 0,
            "clarification_count": 0,
            "thinking_steps": 0
        }
    
    # =========================================================================
    # Public Entry Point (向后兼容同步接口)
    # =========================================================================
    
    def execute(self, research_topic: str, research_objective: str = "") -> Dict[str, Any]:
        """
        Execute research workflow (synchronous entry point).
        
        内部使用 asyncio 运行异步工作流，对外保持同步接口兼容。
        
        Args:
            research_topic: Research topic
            research_objective: Research objective
            
        Returns:
            Dict: Research results
        """
        start_time = time.time()
        
        try:
            # Detect language
            self.language = self._detect_language(research_topic)
            
            # Initialize research context
            self.research_context["topic"] = research_topic
            self.research_context["objective"] = research_objective
            self.research_context["original_topic"] = research_topic
            self.research_context["current_iteration"] = 0
            
            # Run async workflow
            result = self._run_async(self._execute_workflow(research_topic, research_objective))
            
            # Calculate final metrics
            execution_time = time.time() - start_time
            self.metrics["execution_time"] = execution_time
            self.metrics["success_rate"] = 1.0 if result.get("success", False) else 0.0
            
            return result
            
        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}")
            self.metrics["error_count"] += 1
            return {
                "success": False,
                "error": str(e),
                "metrics": self.metrics
            }
    
    async def aexecute(self, research_topic: str, research_objective: str = "") -> Dict[str, Any]:
        """
        Execute research workflow (async entry point).
        
        Args:
            research_topic: Research topic
            research_objective: Research objective
            
        Returns:
            Dict: Research results
        """
        start_time = time.time()
        
        try:
            self.language = self._detect_language(research_topic)
            self.research_context["topic"] = research_topic
            self.research_context["objective"] = research_objective
            self.research_context["original_topic"] = research_topic
            self.research_context["current_iteration"] = 0
            
            result = await self._execute_workflow(research_topic, research_objective)
            
            execution_time = time.time() - start_time
            self.metrics["execution_time"] = execution_time
            self.metrics["success_rate"] = 1.0 if result.get("success", False) else 0.0
            
            return result
            
        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}")
            self.metrics["error_count"] += 1
            return {
                "success": False,
                "error": str(e),
                "metrics": self.metrics
            }
    
    def _run_async(self, coro):
        """Run async coroutine from sync context."""
        try:
            loop = asyncio.get_running_loop()
            # Already in an async context - use nest_asyncio or thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        except RuntimeError:
            # No running loop - safe to use asyncio.run
            return asyncio.run(coro)
    
    # =========================================================================
    # Core Async Workflow
    # =========================================================================
    
    async def _execute_workflow(self, research_topic: str, research_objective: str) -> Dict[str, Any]:
        """Execute research workflow based on selected mode."""
        if self.mode == WorkflowMode.BASIC:
            return await self._execute_basic_mode(research_topic, research_objective)
        elif self.mode == WorkflowMode.INTERACTIVE:
            return await self._execute_interactive_mode(research_topic, research_objective)
        elif self.mode == WorkflowMode.ADVANCED:
            return await self._execute_advanced_mode(research_topic, research_objective)
        else:
            return await self._execute_basic_mode(research_topic, research_objective)
    
    # =========================================================================
    # Basic Mode
    # =========================================================================
    
    async def _execute_basic_mode(self, research_topic: str, research_objective: str) -> Dict[str, Any]:
        """Execute basic research mode - multi-round search loop."""
        self.research_context["current_iteration"] = 0
        
        for iteration in range(self.max_research_loops):
            self.research_context["current_iteration"] = iteration + 1
            self.metrics["loop_count"] = iteration + 1
            
            print(f"\n● Round {iteration + 1}/{self.max_research_loops}")
            
            # Generate search queries
            max_queries = self.config.get('deep_search', {}).get(
                'max_generated_search_query_per_research_loop', 5
            )
            print(f"  ✦ Generating {max_queries} search queries ...")
            queries = await self._generate_search_queries(research_topic, self.research_context, max_queries)
            print(f"  ✦ Generated {len(queries)} search queries")
            for q in queries:
                print(f"  | \033[2m{q}\033[0m")
            
            # Execute search and analysis
            search_results = await self._search_and_analyze(queries, self.research_context)
            
            # Update context
            self.research_context["research_summaries"].extend(search_results.get("findings_summary", []))
            self.research_context["citations"].extend(search_results.get("citations", []))
            self.research_context["thinking_process"].extend(search_results.get("thinking_process", []))
            self.metrics["thinking_steps"] += len(search_results.get("thinking_process", []))
            
            # Check continuation
            if not self._should_continue_research(self.research_context):
                print(f"● Search loop completed in {iteration + 1} rounds\n")
                break
        
        # Generate final report
        print("● Preparing comprehensive research report ...")
        final_report = await self._generate_final_report(self.research_context)
        print("")
        
        return {
            "success": True,
            "mode": "basic",
            "final_report": final_report,
            "metrics": self.metrics,
            "research_context": self.research_context
        }
    
    # =========================================================================
    # Interactive Mode
    # =========================================================================
    
    async def _execute_interactive_mode(self, research_topic: str, research_objective: str) -> Dict[str, Any]:
        """Execute interactive research mode."""
        try:
            # Phase 1: Initial search
            print(f"\n● Initial search and understanding")
            initial_queries = await self._generate_search_queries(research_topic, self.research_context, 3)
            initial_results = await self._search_and_analyze(initial_queries, self.research_context)
            
            self.research_context["thinking_process"].extend(initial_results.get("thinking_process", []))
            
            # Phase 2: Reflection
            print(f"● Reflection and analysis")
            reflection_result = await self._perform_reflection_analysis(
                research_topic, initial_results.get("raw_results", [])
            )
            print(f"  ✦ Reflection completed")
            if isinstance(reflection_result, dict):
                for key, value in reflection_result.items():
                    print(f"     ✦ {key.replace('_', ' ').title()}")
                    if isinstance(value, list):
                        for item in value:
                            print(f"     | \033[2m{item}\033[0m")
                    else:
                        print(f"     | \033[2m{value}\033[0m")
            
            # Phase 3: Topic clarification
            print(f"\n● Topic clarification")
            clarification_result = await self._clarify_research_topic(research_topic, reflection_result)
            
            if clarification_result.get("clarification_success", False):
                self.metrics["clarification_count"] += 1
            
            clarified_topic = clarification_result.get("clarified_topic", research_topic)
            user_answers = clarification_result.get("user_answers", {})
            clarification_success = clarification_result.get("clarification_success", False)
            
            # Phase 4: Continue research
            if clarification_success and clarified_topic != research_topic:
                print(f"\n● Updated research focus: \033[36m{clarified_topic}\033[0m")
                final_result = await self._continue_research_with_clarified_topic(clarified_topic, user_answers)
                
                return {
                    "success": True,
                    "mode": "interactive",
                    "original_topic": research_topic,
                    "clarified_topic": clarified_topic,
                    "user_answers": user_answers,
                    "final_report": final_result.get("final_report", ""),
                    "report_path": final_result.get("report_path", ""),
                    "metrics": self.metrics,
                    "reflection_result": reflection_result,
                    "clarification_result": clarification_result
                }
            else:
                # Fallback to basic mode with remaining iterations
                print(f"\n● Continuing with original topic")
                self.research_context.update({
                    "topic": research_topic,
                    "findings": initial_results.get("findings_summary", []),
                    "knowledge_gaps": initial_results.get("knowledge_gaps", []),
                })
                
                # Continue research loop
                for iteration in range(1, self.max_research_loops):
                    print(f"\n● Research iteration {iteration + 1}/{self.max_research_loops}")
                    self.research_context["current_iteration"] = iteration
                    self.metrics["loop_count"] = iteration + 1
                    
                    queries = await self._generate_search_queries(research_topic, self.research_context, 3)
                    search_results = await self._search_and_analyze(queries, self.research_context)
                    
                    self.research_context["thinking_process"].extend(search_results.get("thinking_process", []))
                    self.metrics["thinking_steps"] += len(search_results.get("thinking_process", []))
                    
                    if not self._should_continue_research(self.research_context):
                        break
                
                # Generate final report
                final_report = await self._generate_final_report(self.research_context)
                report_path = self._save_report_to_file(final_report, research_topic, "_interactive")
                
                return {
                    "success": True,
                    "mode": "interactive",
                    "original_topic": research_topic,
                    "clarified_topic": research_topic,
                    "user_answers": user_answers,
                    "final_report": final_report,
                    "report_path": report_path,
                    "metrics": self.metrics,
                    "reflection_result": reflection_result,
                    "clarification_result": clarification_result
                }
            
        except Exception as e:
            self.logger.error(f"Interactive mode failed, falling back to basic mode: {e}")
            self.metrics["error_count"] += 1
            return await self._execute_basic_mode(research_topic, research_objective)
    
    # =========================================================================
    # Advanced Mode
    # =========================================================================
    
    async def _execute_advanced_mode(self, research_topic: str, research_objective: str) -> Dict[str, Any]:
        """Execute advanced research mode - Multi-iteration with quality assessment."""
        try:
            max_iterations = self.kwargs.get('max_iterations', 3)
            quality_threshold = self.kwargs.get('quality_threshold', 0.8)
            
            all_iterations = []
            accumulated_knowledge: Dict[str, Any] = {}
            total_search_results = []
            
            for iteration in range(1, max_iterations + 1):
                print(f"\n● Iteration {iteration}/{max_iterations}")
                self.metrics["loop_count"] = iteration
                
                # Execute single iteration
                iteration_result = await self._execute_single_iteration(
                    research_topic, iteration, accumulated_knowledge, research_objective
                )
                
                all_iterations.append(iteration_result)
                total_search_results.extend(iteration_result.get('search_results', []))
                
                self.metrics["thinking_steps"] += len(
                    self.research_context.get("thinking_process", [])
                )
                
                # Update accumulated knowledge
                self._update_accumulated_knowledge(accumulated_knowledge, iteration_result)
                
                # Perform reflection
                reflection = self._perform_iteration_reflection(
                    iteration, iteration_result, accumulated_knowledge
                )
                
                # Check termination
                should_terminate, reason = self._check_advanced_termination(
                    iteration, iteration_result, quality_threshold, max_iterations
                )
                
                if should_terminate:
                    print(f"● Research terminated: {reason}")
                    break
                
                # Adjust strategy
                if iteration < max_iterations:
                    self._adjust_next_iteration_strategy(reflection, accumulated_knowledge)
            
            # Generate final report
            print("● Preparing comprehensive advanced research report...")
            advanced_context = {
                "topic": research_topic,
                "objective": research_objective,
                "current_iteration": len(all_iterations),
                "research_summaries": [],
                "thinking_process": [],
                "citations": []
            }
            
            for iteration_result in all_iterations:
                for result in iteration_result.get('search_results', []):
                    if isinstance(result, dict):
                        advanced_context["research_summaries"].append({
                            "title": result.get("title", ""),
                            "content": result.get("content", "") or result.get("snippet", ""),
                            "url": result.get("url", "")
                        })
            
            insights = accumulated_knowledge.get('insights', [])
            advanced_context["thinking_process"].extend(insights)
            
            final_report = await self._generate_final_report(advanced_context)
            
            return {
                'success': True,
                'mode': 'advanced',
                'research_topic': research_topic,
                'total_iterations': len(all_iterations),
                'iterations': all_iterations,
                'final_report': final_report,
                'total_search_results': len(total_search_results),
                'accumulated_knowledge': accumulated_knowledge,
                'execution_status': 'completed',
                'metrics': self.metrics
            }
            
        except Exception as e:
            self.logger.error(f"Advanced mode failed: {e}")
            print(f"● Advanced mode failed: {e}, falling back to basic mode")
            return await self._execute_basic_mode(research_topic, research_objective)
    
    # =========================================================================
    # Core Search & Analysis (新异步实现)
    # =========================================================================
    
    async def _generate_search_queries(
        self, topic: str, context: Dict[str, Any], max_queries: int = 5
    ) -> List[str]:
        """Generate search queries using LLM."""
        existing_knowledge = context.get("research_summaries", [])
        knowledge_gaps = context.get("knowledge_gaps", [])
        thinking_insights = context.get("thinking_insights", [])
        
        existing_summary_text = ""
        if existing_knowledge:
            summaries = [self._get_summary_content(s) for s in existing_knowledge[-2:]]
            existing_summary_text = "\n".join(f"- {s}" for s in summaries)
        
        knowledge_gaps_text = ""
        if knowledge_gaps:
            knowledge_gaps_text = "\n".join(f"- {gap}" for gap in knowledge_gaps[-3:])
        
        thinking_insights_text = ""
        if thinking_insights:
            all_insights = []
            for insight_list in thinking_insights[-2:]:
                if isinstance(insight_list, list):
                    all_insights.extend(insight_list)
            if all_insights:
                thinking_insights_text = "\n".join(f"- {i}" for i in all_insights[-5:])
        
        if self.language == "zh":
            prompt = f"""作为专业的搜索策略专家，请严格生成{max_queries}个高质量的搜索查询。

研究主题：{topic}

已有知识：
{existing_summary_text if existing_summary_text else "无"}

知识缺口：
{knowledge_gaps_text if knowledge_gaps_text else "无"}

思考见解：
{thinking_insights_text if thinking_insights_text else "无"}

要求：
1. 覆盖主题的不同方面
2. 使用不同的关键词组合
3. 针对知识缺口设计查询
4. 查询应简洁且有针对性

请以JSON格式返回：{{"queries": ["查询1", ...]}}
只返回JSON。"""
        else:
            prompt = f"""As a search strategy expert, generate {max_queries} high-quality search queries.

Research Topic: {topic}

Existing Knowledge:
{existing_summary_text if existing_summary_text else "None"}

Knowledge Gaps:
{knowledge_gaps_text if knowledge_gaps_text else "None"}

Thinking Insights:
{thinking_insights_text if thinking_insights_text else "None"}

Requirements:
1. Cover different aspects of the topic
2. Use different keyword combinations
3. Target identified knowledge gaps
4. Queries should be concise and targeted

Return in JSON: {{"queries": ["query1", ...]}}
Return only JSON."""
        
        try:
            response = await self.llm_provider.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            result = self._safe_json_parse(content)
            
            if result and isinstance(result, dict) and "queries" in result:
                queries = result["queries"][:max_queries]
                return [q for q in queries if isinstance(q, str) and q.strip()]
        except Exception as e:
            self.logger.error(f"Query generation failed: {e}")
        
        # Fallback
        return [f"{topic} latest research", f"{topic} detailed analysis", f"{topic} trends"]
    
    async def _search_and_analyze(
        self, queries: List[str], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute search and analysis with thinking process."""
        all_results: List[Dict[str, Any]] = []
        thinking_process: List[str] = []
        raw_results: List[Dict[str, Any]] = []
        
        max_search_results = self.config.get('deep_search', {}).get('max_search_results', 10)
        
        for i, query in enumerate(queries, 1):
            print(f"  ✦ Searching: \033[36m{query}\033[0m")
            
            try:
                # Execute search using new tool interface
                search_response = self.search_tool.run(
                    query=query,
                    max_results=max_search_results
                )
                
                # Parse response (SearchResponse dict format)
                if isinstance(search_response, dict):
                    results_list = search_response.get("results", [])
                elif isinstance(search_response, list):
                    results_list = search_response
                else:
                    results_list = []
                
                raw_results.extend(results_list)
                all_results.extend(results_list)
                
            except Exception as e:
                print(f"\n\033[31m  Search error: {e}\033[0m")
                results_list = []
            
            # Perform thinking analysis
            try:
                if results_list:
                    print(f"  ✦ Thinking ...")
                    thinking_result = await self._perform_search_analysis_thinking(
                        query, results_list, context
                    )
                    thinking_process.append(thinking_result["thinking"])
                    print(f"  ✦ Insight: {thinking_result['thinking'][:100]}...\n")
                    
                    # Update context with insights
                    if "thinking_insights" not in context:
                        context["thinking_insights"] = []
                    context["thinking_insights"].append(thinking_result.get("insights", []))
                    
                    # Update knowledge gaps
                    if thinking_result.get("knowledge_gaps"):
                        if "knowledge_gaps" not in context:
                            context["knowledge_gaps"] = []
                        context["knowledge_gaps"].extend(thinking_result["knowledge_gaps"])
                
                self.metrics["search_count"] += 1
                
            except Exception as e:
                self.logger.error(f"Analysis failed: {e}")
                self.metrics["error_count"] += 1
        
        # Build citations
        citations = []
        for result in all_results:
            if isinstance(result, dict):
                url = result.get('url', '')
                title = result.get('title', '')
                if url and title:
                    citations.append(f"[{title}]({url})")
        
        # Build findings summary
        findings_summary = []
        for result in all_results:
            content = ""
            if isinstance(result, dict):
                content = result.get('content', '') or result.get('snippet', '')
            if content:
                findings_summary.append({
                    "title": result.get("title", ""),
                    "content": content,
                    "url": result.get("url", "")
                })
        
        return {
            "results": all_results,
            "raw_results": raw_results,
            "findings_summary": findings_summary,
            "citations": citations,
            "thinking_process": thinking_process,
            "knowledge_gaps": context.get("knowledge_gaps", [])
        }
    
    async def _perform_search_analysis_thinking(
        self, query: str, search_results: List[Dict], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform LLM-based analysis of search results."""
        try:
            results_summary = ""
            for i, result in enumerate(search_results[:5], 1):
                title = result.get('title', 'No title')
                content = result.get('content', '') or result.get('snippet', '')
                url = result.get('url', '')
                results_summary += f"{i}. {title}\n"
                if content:
                    results_summary += f"   Content: {content[:200]}...\n"
                if url:
                    results_summary += f"   URL: {url}\n"
                results_summary += "\n"
            
            research_topic = context.get("topic", "")
            existing_insights = context.get("thinking_insights", [])
            knowledge_gaps = context.get("knowledge_gaps", [])
            language = self._detect_language(research_topic)
            
            if language == "zh":
                prompt = f"""作为研究分析专家，请分析以下搜索结果。

研究主题：{research_topic}
搜索查询：{query}

搜索结果：
{results_summary}

请以JSON格式返回：
{{"thinking": "分析思考过程", "insights": ["见解1", "见解2"], "knowledge_gaps": ["缺口1"]}}
只返回JSON。"""
            else:
                prompt = f"""As a research analyst, analyze the following search results.

Research Topic: {research_topic}
Search Query: {query}

Search Results:
{results_summary}

Return in JSON:
{{"thinking": "analysis process", "insights": ["insight1", "insight2"], "knowledge_gaps": ["gap1"]}}
Return only JSON."""
            
            response = await self.llm_provider.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            result = self._safe_json_parse(content)
            
            if result and isinstance(result, dict):
                return {
                    "thinking": result.get("thinking", f"Analyzed {len(search_results)} results for '{query}'"),
                    "insights": result.get("insights", []),
                    "knowledge_gaps": result.get("knowledge_gaps", [])
                }
            
        except Exception as e:
            self.logger.error(f"Thinking analysis failed: {e}")
        
        return {
            "thinking": f"Analyzed {len(search_results)} results for '{query}'",
            "insights": [],
            "knowledge_gaps": []
        }
    
    # =========================================================================
    # Report Generation
    # =========================================================================
    
    async def _generate_final_report(self, context: Dict[str, Any]) -> str:
        """Generate comprehensive final research report."""
        try:
            # Convert to ResearchContext model
            research_context = self._convert_to_research_context(context)
            
            # Generate sub-reports
            sub_reports = await self._generate_sub_reports(research_context)
            
            # Build comprehensive report
            final_report = self._build_comprehensive_report(research_context, sub_reports)
            
            # Save sub-reports
            self._save_sub_reports(sub_reports, context.get("topic", "research"))
            
            return final_report
            
        except Exception as e:
            self.logger.error(f"Report generation failed: {e}")
            return self._create_fallback_report(context)
    
    def _convert_to_research_context(self, context: Dict[str, Any]) -> ResearchContext:
        """Convert workflow context dict to ResearchContext model."""
        search_results = []
        for summary in context.get("research_summaries", []):
            if isinstance(summary, dict):
                result = SearchResult(
                    title=summary.get("title", "Search Result"),
                    url=summary.get("url", ""),
                    snippet=summary.get("content", str(summary)),
                    source=SearchEngine.MOCK,
                    content=summary.get("content", str(summary))
                )
                search_results.append(result)
        
        iteration = ResearchIteration(
            iteration_id=context.get("current_iteration", 1),
            queries=[],
            search_results=search_results,
            analysis_summary="\n".join(context.get("thinking_process", [])),
            identified_gaps=[],
            phase=ResearchPhase.SEARCH_EXECUTION
        )
        
        research_context = ResearchContext(
            research_topic=context.get("topic", ""),
            research_objective=context.get("objective", ""),
            iterations=[iteration]
        )
        
        return research_context
    
    async def _generate_sub_reports(self, research_context: ResearchContext) -> Dict[str, str]:
        """Generate multiple sub-reports."""
        sub_reports = {}
        language = self._detect_language(research_context.research_topic)
        
        print("  ✦ Generating executive summary...")
        sub_reports["executive_summary"] = await self._generate_executive_summary(research_context, language)
        
        print("  ✦ Generating detailed analysis...")
        sub_reports["detailed_analysis"] = await self._generate_detailed_analysis(research_context, language)
        
        print("  ✦ Generating methodology report...")
        sub_reports["methodology"] = await self._generate_methodology_report(research_context, language)
        
        print("  ✦ Generating findings summary...")
        sub_reports["findings"] = await self._generate_findings_report(research_context, language)
        
        print("  ✦ Generating implications analysis...")
        sub_reports["implications"] = await self._generate_implications_report(research_context, language)
        
        return sub_reports
    
    async def _generate_executive_summary(self, context: ResearchContext, language: str) -> str:
        """Generate executive summary."""
        all_results = context.get_all_search_results()
        key_findings = "\n".join([r.snippet[:200] for r in all_results[:5]])
        
        if language == "zh":
            prompt = f"""作为研究报告专家，请为以下研究撰写执行摘要（800-1200字）。

研究主题：{context.research_topic}
研究目标：{context.research_objective}

关键发现：
{key_findings}

包含：研究背景、核心发现（3-5个）、主要结论、实践意义、建议行动。
语言简洁专业。"""
        else:
            prompt = f"""As a research report expert, write an executive summary (800-1200 words).

Research Topic: {context.research_topic}
Objective: {context.research_objective}

Key Findings:
{key_findings}

Include: background, core findings (3-5), conclusions, implications, recommended actions.
Professional and concise."""
        
        try:
            response = await self.llm_provider.ainvoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            return f"Executive summary generation failed: {e}"
    
    async def _generate_detailed_analysis(self, context: ResearchContext, language: str) -> str:
        """Generate detailed analysis."""
        all_results = context.get_all_search_results()
        detailed_content = "\n\n".join([f"**{r.title}**\n{r.content}" for r in all_results[:10]])
        
        if language == "zh":
            prompt = f"""作为深度研究分析专家，请撰写深度分析报告（2000-3000字）。

研究主题：{context.research_topic}
研究内容：
{detailed_content}

包含：现状分析、深度洞察、挑战与机遇、趋势预测。"""
        else:
            prompt = f"""As a research analyst, write a detailed analysis (2000-3000 words).

Research Topic: {context.research_topic}
Content:
{detailed_content}

Include: current state, deep insights, challenges & opportunities, trend predictions."""
        
        try:
            response = await self.llm_provider.ainvoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            return f"Detailed analysis generation failed: {e}"
    
    async def _generate_methodology_report(self, context: ResearchContext, language: str) -> str:
        """Generate methodology report."""
        search_count = len(context.get_all_search_results())
        iteration_count = len(context.iterations)
        
        if language == "zh":
            prompt = f"""作为研究方法学专家，请撰写方法论报告（1000-1500字）。

研究主题：{context.research_topic}
研究轮次：{iteration_count}轮
搜索结果：{search_count}条

包含：研究设计、数据收集方法、质量保证、分析方法、局限性。"""
        else:
            prompt = f"""As a methodology expert, write a methodology report (1000-1500 words).

Research Topic: {context.research_topic}
Rounds: {iteration_count}
Results: {search_count} items

Include: research design, data collection, quality assurance, analysis methods, limitations."""
        
        try:
            response = await self.llm_provider.ainvoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            return f"Methodology report generation failed: {e}"
    
    async def _generate_findings_report(self, context: ResearchContext, language: str) -> str:
        """Generate findings report."""
        all_results = context.get_all_search_results()
        findings_text = "\n".join([f"- {r.title}: {r.snippet[:150]}" for r in all_results[:10]])
        
        if language == "zh":
            prompt = f"""作为研究发现分析专家，请撰写发现报告（1500-2000字）。

研究主题：{context.research_topic}
发现摘要：
{findings_text}

包含：核心发现概述、分类详细发现、数据支撑、发现关联性、意外发现。"""
        else:
            prompt = f"""As a findings analyst, write a findings report (1500-2000 words).

Research Topic: {context.research_topic}
Findings:
{findings_text}

Include: core findings, categorized details, data support, interconnections, unexpected discoveries."""
        
        try:
            response = await self.llm_provider.ainvoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            return f"Findings report generation failed: {e}"
    
    async def _generate_implications_report(self, context: ResearchContext, language: str) -> str:
        """Generate implications and recommendations report."""
        if language == "zh":
            prompt = f"""作为战略分析专家，请撰写影响分析报告（1200-1800字）。

研究主题：{context.research_topic}

包含：对不同利益相关方的影响、行动建议（短中长期）、风险提示、监测指标。"""
        else:
            prompt = f"""As a strategic analyst, write an implications report (1200-1800 words).

Research Topic: {context.research_topic}

Include: stakeholder impacts, action recommendations (short/mid/long term), risk alerts, monitoring indicators."""
        
        try:
            response = await self.llm_provider.ainvoke(prompt)
            return response.content if hasattr(response, 'content') else str(response)
        except Exception as e:
            return f"Implications report generation failed: {e}"
    
    def _build_comprehensive_report(self, context: ResearchContext, sub_reports: Dict[str, str]) -> str:
        """Build the final comprehensive report."""
        language = self._detect_language(context.research_topic)
        
        if language == "zh":
            report = f"""# {context.research_topic} - 综合研究报告

## 报告概述

本报告通过多轮深度研究，对"{context.research_topic}"进行了全面系统的分析。

### 研究规模
- 研究轮次：{len(context.iterations)}轮
- 信息来源：{len(context.get_all_search_results())}个
- 报告生成时间：{datetime.now().strftime('%Y年%m月%d日')}

---

## 一、执行摘要

{sub_reports.get('executive_summary', '生成中...')}

---

## 二、研究方法论

{sub_reports.get('methodology', '生成中...')}

---

## 三、核心发现

{sub_reports.get('findings', '生成中...')}

---

## 四、深度分析

{sub_reports.get('detailed_analysis', '生成中...')}

---

## 五、影响分析与建议

{sub_reports.get('implications', '生成中...')}

---

## 六、研究总结

本研究通过系统性的信息收集和分析，对{context.research_topic}形成了全面深入的认知。

---

*本报告由 AgenticX Deep Research System v2 生成*
*生成时间：{datetime.now().isoformat()}*
"""
        else:
            report = f"""# {context.research_topic} - Comprehensive Research Report

## Report Overview

This report conducts a comprehensive analysis of "{context.research_topic}" through multi-round deep research.

### Research Scale
- Research Rounds: {len(context.iterations)} rounds
- Information Sources: {len(context.get_all_search_results())} items
- Report Generated: {datetime.now().strftime('%Y-%m-%d')}

---

## I. Executive Summary

{sub_reports.get('executive_summary', 'Generating...')}

---

## II. Research Methodology

{sub_reports.get('methodology', 'Generating...')}

---

## III. Core Findings

{sub_reports.get('findings', 'Generating...')}

---

## IV. Detailed Analysis

{sub_reports.get('detailed_analysis', 'Generating...')}

---

## V. Implications & Recommendations

{sub_reports.get('implications', 'Generating...')}

---

## VI. Research Summary

This research provides comprehensive insights into {context.research_topic}.

---

*Generated by AgenticX Deep Research System v2*
*Generated at: {datetime.now().isoformat()}*
"""
        return report
    
    # =========================================================================
    # Interactive Mode Helpers
    # =========================================================================
    
    async def _perform_reflection_analysis(
        self, research_topic: str, initial_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Perform reflection analysis on initial search results."""
        try:
            key_findings = []
            for result in initial_results[:5]:
                content = result.get('content', '') or result.get('snippet', '')
                if content:
                    sentences = content.split('.')[:3]
                    key_findings.extend([s.strip() for s in sentences if len(s.strip()) > 10])
            
            if self.language == "zh":
                prompt = f"""作为研究分析师，请分析以下初步搜索结果：{research_topic}

关键发现：
{chr(10).join(key_findings[:10])}

请以JSON格式返回：
{{"key_aspects": ["方面1", "方面2"], "potential_interests": ["兴趣1", "兴趣2"], "suggested_clarifications": ["方向1"], "reflection": "总结"}}
只返回JSON。"""
            else:
                prompt = f"""As a research analyst, analyze initial results for: {research_topic}

Key findings:
{chr(10).join(key_findings[:10])}

Return in JSON:
{{"key_aspects": ["aspect1", "aspect2"], "potential_interests": ["interest1", "interest2"], "suggested_clarifications": ["direction1"], "reflection": "summary"}}
Return only JSON."""
            
            response = await self.llm_provider.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            result = self._safe_json_parse(content)
            
            if result and isinstance(result, dict):
                return result
                
        except Exception as e:
            self.logger.error(f"Reflection analysis failed: {e}")
        
        return {
            "key_aspects": ["基本概念", "应用场景", "发展趋势"],
            "potential_interests": ["实际应用", "技术细节"],
            "suggested_clarifications": ["具体关注点"],
            "reflection": f"已完成对{research_topic}的初步分析"
        }
    
    async def _clarify_research_topic(
        self, research_topic: str, reflection_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Clarify research topic based on reflection."""
        print("  ✦ Preparing topic clarification questions")
        
        try:
            key_aspects = reflection_result.get("key_aspects", [])
            potential_interests = reflection_result.get("potential_interests", [])
            suggested_clarifications = reflection_result.get("suggested_clarifications", [])
            
            if self.language == "zh":
                prompt = f"""作为研究顾问，请根据以下信息生成3个澄清问题。

原始问题：{research_topic}
关键方面：{', '.join(key_aspects)}
用户可能关心：{', '.join(potential_interests)}
建议澄清方向：{', '.join(suggested_clarifications)}

以JSON格式返回：{{"questions": ["问题1", "问题2", "问题3"]}}
只返回JSON。"""
            else:
                prompt = f"""As a research consultant, generate 3 clarification questions.

Original topic: {research_topic}
Key aspects: {', '.join(key_aspects)}
Potential interests: {', '.join(potential_interests)}
Suggested directions: {', '.join(suggested_clarifications)}

Return in JSON: {{"questions": ["q1", "q2", "q3"]}}
Return only JSON."""
            
            response = await self.llm_provider.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            result = self._safe_json_parse(content)
            
            questions = []
            if result and isinstance(result, dict):
                questions = result.get("questions", [])
            
            if not questions:
                questions = ["What specific aspect interests you most?"]
            
            # Ask user for answers
            user_answers = {}
            print(f"\n  To better focus the research, please answer:")
            for i, question in enumerate(questions[:3], 1):
                print(f"  | Q{i}: {question}")
                try:
                    answer = input("  | Your answer: ").strip()
                    if answer:
                        user_answers[f"question_{i}"] = answer
                    else:
                        user_answers[f"question_{i}"] = "No specific preference"
                except (EOFError, KeyboardInterrupt):
                    user_answers[f"question_{i}"] = "No specific preference"
            
            # Generate clarified topic
            if any(v != "No specific preference" for v in user_answers.values()):
                clarified_topic = await self._generate_clarified_topic(research_topic, user_answers)
                return {
                    "clarified_topic": clarified_topic,
                    "user_answers": user_answers,
                    "clarification_success": True
                }
            
            return {
                "clarified_topic": research_topic,
                "user_answers": user_answers,
                "clarification_success": False
            }
            
        except Exception as e:
            self.logger.error(f"Topic clarification failed: {e}")
            return {
                "clarified_topic": research_topic,
                "user_answers": {},
                "clarification_success": False
            }
    
    async def _generate_clarified_topic(self, original_topic: str, user_answers: Dict[str, str]) -> str:
        """Generate clarified topic based on user answers."""
        answers_text = "\n".join(f"- {q}: {a}" for q, a in user_answers.items())
        
        if self.language == "zh":
            prompt = f"""根据用户回答，生成一个更精确的研究主题（不超过20字）。

原始主题：{original_topic}
用户回答：
{answers_text}

直接返回新主题，不要解释。"""
        else:
            prompt = f"""Based on user answers, generate a more precise research topic (max 30 words).

Original: {original_topic}
Answers:
{answers_text}

Return only the new topic."""
        
        try:
            response = await self.llm_provider.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            return content.strip()
        except Exception:
            return original_topic
    
    async def _continue_research_with_clarified_topic(
        self, clarified_topic: str, user_answers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Continue research with clarified topic."""
        try:
            research_context = self._get_initial_research_context()
            research_context["topic"] = clarified_topic
            research_context["original_topic"] = self.research_context.get("original_topic", clarified_topic)
            
            # Generate targeted queries
            print(f"  ✦ Generating targeted queries ...")
            targeted_queries = await self._generate_targeted_queries(clarified_topic, user_answers)
            print(f"  ✦ Generated {len(targeted_queries)} targeted queries")
            for q in targeted_queries:
                print(f"  | \033[2m{q}\033[0m")
            
            # Execute research loop
            for iteration in range(self.max_research_loops):
                print(f"\n● Research iteration {iteration + 1}/{self.max_research_loops}")
                research_context["current_iteration"] = iteration
                
                if iteration == 0:
                    current_queries = targeted_queries
                else:
                    current_queries = await self._generate_search_queries(clarified_topic, research_context, 3)
                
                search_results = await self._search_and_analyze(current_queries, research_context)
                
                research_context["search_history"].extend(current_queries)
                research_context["knowledge_gaps"] = search_results.get("knowledge_gaps", [])
                research_context["thinking_process"].extend(search_results.get("thinking_process", []))
                research_context["research_summaries"].extend(search_results.get("findings_summary", []))
                research_context["citations"].extend(search_results.get("citations", []))
                
                if not self._should_continue_research(research_context):
                    break
            
            # Generate report
            print(" ● Generating comprehensive research report ...")
            final_report = await self._generate_final_report(research_context)
            report_path = self._save_report_to_file(final_report, clarified_topic, "_clarified")
            
            return {
                "success": True,
                "clarified_topic": clarified_topic,
                "final_report": final_report,
                "report_path": report_path,
                "metrics": self.metrics
            }
            
        except Exception as e:
            self.logger.error(f"Clarified research failed: {e}")
            return {"success": False, "error": str(e), "final_report": ""}
    
    async def _generate_targeted_queries(self, clarified_topic: str, user_answers: Dict[str, str]) -> List[str]:
        """Generate targeted queries based on clarified topic."""
        preferences = "\n".join([f"- {k}: {v}" for k, v in user_answers.items() if v != "No specific preference"])
        
        if self.language == "zh":
            prompt = f"""生成5个针对性搜索查询。

研究主题：{clarified_topic}
用户偏好：
{preferences}

以JSON格式返回：{{"queries": ["查询1", ...]}}
只返回JSON。"""
        else:
            prompt = f"""Generate 5 targeted search queries.

Topic: {clarified_topic}
Preferences:
{preferences}

Return in JSON: {{"queries": ["query1", ...]}}
Return only JSON."""
        
        try:
            response = await self.llm_provider.ainvoke(prompt)
            content = response.content if hasattr(response, 'content') else str(response)
            result = self._safe_json_parse(content)
            if result and "queries" in result:
                return result["queries"][:5]
        except Exception:
            pass
        
        return [clarified_topic]
    
    # =========================================================================
    # Advanced Mode Helpers
    # =========================================================================
    
    async def _execute_single_iteration(
        self, research_topic: str, iteration: int,
        accumulated_knowledge: Dict[str, Any], research_objective: str
    ) -> Dict[str, Any]:
        """Execute a single iteration in advanced mode."""
        print(f"  ● Starting iteration {iteration}")
        
        # Generate queries
        if iteration == 1:
            queries = await self._generate_search_queries(research_topic, self.research_context, 5)
        else:
            # Focus on knowledge gaps
            gaps = accumulated_knowledge.get('knowledge_gaps', [])
            if gaps:
                gap_context = dict(self.research_context)
                gap_context["knowledge_gaps"] = gaps[:3]
                queries = await self._generate_search_queries(research_topic, gap_context, 5)
            else:
                queries = await self._generate_search_queries(research_topic, self.research_context, 5)
        
        # Execute search
        search_results = await self._search_and_analyze(queries, self.research_context)
        
        # Update thinking process
        self.research_context.setdefault("thinking_process", []).extend(
            search_results.get("thinking_process", [])
        )
        
        # Calculate quality score
        quality_score = self._calculate_iteration_quality(search_results)
        
        return {
            'iteration': iteration,
            'queries': queries,
            'search_results': search_results.get('results', []),
            'quality_score': quality_score,
            'new_insights': search_results.get("thinking_process", []),
            'knowledge_gaps': search_results.get("knowledge_gaps", [])
        }
    
    def _calculate_iteration_quality(self, search_results: Dict[str, Any]) -> float:
        """Calculate quality score for an iteration."""
        results = search_results.get('results', [])
        insights = search_results.get('thinking_process', [])
        
        result_score = min(len(results) * 0.05, 0.5)
        insight_score = min(len(insights) * 0.15, 0.5)
        
        return min(result_score + insight_score, 1.0)
    
    def _perform_iteration_reflection(
        self, iteration: int, iteration_result: Dict[str, Any],
        accumulated_knowledge: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Perform reflection for current iteration."""
        quality_score = iteration_result.get('quality_score', 0.0)
        gaps = iteration_result.get('knowledge_gaps', [])
        
        if quality_score >= 0.8:
            next_strategy = "maintain_current_approach"
        elif quality_score >= 0.6:
            next_strategy = "expand_search_scope"
        else:
            next_strategy = "change_search_strategy"
        
        return {
            'iteration': iteration,
            'quality_assessment': quality_score,
            'identified_gaps': gaps,
            'next_strategy': next_strategy,
            'confidence_level': 'high' if quality_score >= 0.7 else 'medium' if quality_score >= 0.5 else 'low'
        }
    
    def _check_advanced_termination(
        self, iteration: int, iteration_result: Dict[str, Any],
        quality_threshold: float, max_iterations: int
    ) -> tuple:
        """Check if advanced mode should terminate."""
        if iteration >= max_iterations:
            return True, "Maximum iterations reached"
        
        quality_score = iteration_result.get('quality_score', 0.0)
        if quality_score >= quality_threshold:
            return True, f"Quality threshold ({quality_threshold}) achieved"
        
        if iteration > 1 and len(iteration_result.get('search_results', [])) == 0:
            return True, "No new information found"
        
        return False, ""
    
    def _adjust_next_iteration_strategy(
        self, reflection: Dict[str, Any], accumulated_knowledge: Dict[str, Any]
    ) -> None:
        """Adjust strategy for next iteration."""
        strategy = reflection.get('next_strategy', 'maintain_current_approach')
        if strategy == "expand_search_scope":
            print("  ● Strategy: Expanding search scope")
        elif strategy == "change_search_strategy":
            print("  ● Strategy: Changing search approach")
        else:
            print("  ● Strategy: Maintaining current approach")
    
    def _update_accumulated_knowledge(
        self, accumulated_knowledge: Dict[str, Any], iteration_result: Dict[str, Any]
    ) -> None:
        """Update accumulated knowledge."""
        accumulated_knowledge.setdefault('insights', []).extend(
            iteration_result.get('new_insights', [])
        )
        accumulated_knowledge['knowledge_gaps'] = iteration_result.get('knowledge_gaps', [])
        accumulated_knowledge.setdefault('quality_scores', []).append(
            iteration_result.get('quality_score', 0.0)
        )
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _should_continue_research(self, context: Dict[str, Any]) -> bool:
        """Determine if research should continue."""
        current_iteration = context.get("current_iteration", 0)
        max_iterations = context.get("max_iterations", self.max_research_loops)
        return current_iteration < max_iterations
    
    def _get_summary_content(self, summary: Any) -> str:
        """Safely get summary content."""
        if isinstance(summary, dict):
            return summary.get('content', '') or summary.get('summary', str(summary))
        elif isinstance(summary, str):
            return summary
        else:
            return str(summary)
    
    def _detect_language(self, text: str) -> str:
        """Detect text language."""
        if not text:
            return "en"
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_chars = sum(1 for c in text if c.strip())
        if total_chars == 0:
            return "en"
        return "zh" if chinese_chars / total_chars > 0.3 else "en"
    
    def _save_report_to_file(self, report_content: str, research_topic: str, suffix: str = "") -> str:
        """Save report to file."""
        try:
            output_dir = Path("./output")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            safe_topic = re.sub(r'[^\w\s-]', '', research_topic)[:50]
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"research_report_{safe_topic}_{timestamp}{suffix}.md"
            file_path = output_dir / filename
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            if file_path.exists():
                file_size = file_path.stat().st_size
                print(f"\n● Report saved to: {file_path}")
                print(f"● File size: {file_size:,} bytes\n")
                return str(file_path)
            return ""
        except Exception as e:
            self.logger.error(f"Failed to save report: {e}")
            return ""
    
    def _save_sub_reports(self, sub_reports: Dict[str, str], topic: str):
        """Save sub-reports as separate files."""
        try:
            output_dir = Path("./output/sub_reports")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            safe_topic = re.sub(r'[^\w\s-]', '', topic)[:30]
            
            for report_type, content in sub_reports.items():
                filename = f"{safe_topic}_{report_type}_{timestamp}.md"
                file_path = output_dir / filename
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
        except Exception as e:
            self.logger.error(f"Failed to save sub-reports: {e}")
    
    def _create_fallback_report(self, context: Dict[str, Any]) -> str:
        """Create fallback report."""
        topic = context.get("topic", "Unknown Topic")
        language = self._detect_language(topic)
        
        if language == "zh":
            return f"""# 研究报告：{topic}

## 执行摘要
本报告展示了对{topic}的研究发现。

## 研究过程
研究采用系统性方法，通过多次搜索迭代进行。

## 主要发现
基于研究，已识别出关键发现。

## 结论
研究为{topic}提供了有价值的见解。

---
*报告生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}*
"""
        else:
            return f"""# Research Report: {topic}

## Executive Summary
This report presents findings from research on {topic}.

## Research Process
Research was conducted using a systematic approach with multiple iterations.

## Key Findings
Based on the research, several key findings have been identified.

## Conclusions
The research provides valuable insights into {topic}.

---
*Report generated on {time.strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    def _safe_json_parse(self, content: str) -> Optional[Dict[str, Any]]:
        """Safely parse JSON content."""
        try:
            cleaned = self._clean_json_response(content)
            return json.loads(cleaned)
        except json.JSONDecodeError:
            try:
                cleaned = self._clean_json_response(content)
                fixed = re.sub(r',\s*}', '}', cleaned)
                fixed = re.sub(r',\s*]', ']', fixed)
                return json.loads(fixed)
            except Exception:
                pass
        except Exception:
            pass
        return None
    
    def _clean_json_response(self, response_content: str) -> str:
        """Clean JSON response content."""
        content = response_content.strip()
        
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            return json_match.group(1).strip()
        
        code_match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
        if code_match:
            return code_match.group(1).strip()
        
        json_object_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
        if json_object_match:
            return json_object_match.group(0).strip()
        
        return content
    
    def _spinner(self, done: threading.Event, message: str = "Loading..."):
        """Display a spinner animation."""
        sys.stdout.write(f"{message}\n")
        sys.stdout.flush()
        
        spinner_chars = ['|\r', '/\r', '-\r', '\\\r']
        i = 0
        while not done.is_set():
            sys.stdout.write(spinner_chars[i % len(spinner_chars)])
            sys.stdout.flush()
            time.sleep(0.1)
            i += 1
        
        sys.stdout.write('\r' + ' ' * 4 + '\r')
        sys.stdout.flush()
