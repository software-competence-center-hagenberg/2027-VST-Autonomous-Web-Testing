from abc import ABC, abstractmethod
import asyncio
import base64
import json
import logging
import textwrap
import os
from pathlib import Path
from datetime import datetime

from agents.browser_manager import BrowserManager
from browser_use import Browser
from browser_use import ChatOpenAI, ChatAzureOpenAI
from browser_use.browser.video_recorder import VideoRecorderService

from openai import AsyncOpenAI

from typing import AsyncIterator, Sequence, Any
from agents.agents import BaseAgent, BrowserAgent, CompletionAgent, ToolAgent, AgentDecision, AgentContext, InteractionMode
from agents.loop import run_agents_loop
from agents.tools import GetCurrentURLTool, DomContainsTextTool, DomExistsSelectorTool, DomCountSelectorTool, DomGetTextTool, FindElementsByIdTool, FindElementsByIdHTMLTool, GetAllIdsTool
from agents.special_tools import StopTool, handle_stop, PerformActionTool, handle_perform_action
from agents.model_configuration import ModelConfiguration
from events import Event
from browser_stream import get_browser_stream

logger = logging.getLogger(__name__)

class AgentConfiguration(ABC):
    """
    Base class for defining (multi-)agent configurations.
    Subclasses define exactly which agents are included and how they are instantiated.
    """

    stop_agent_name: str | None = None

    def __init__(self, llm: ModelConfiguration, num_task_executions: int, max_iterations: int = 500, vision_enabled: bool = True):
        self.llm = llm
        self.num_task_executions = num_task_executions      # how many times a task shall be executed
        self.max_iterations = max_iterations                # how many iterations of the agent loop shall be performed
        self.vision_enabled = vision_enabled                # whether the browser agent should work multimodal or text only
        self._browser_manager: BrowserManager | None = None
        self.last_statistics: dict[str, Any] = {}

    @abstractmethod
    async def setup_context(self, task: str, browser_manager: BrowserManager) -> AgentContext:
        pass

    @abstractmethod
    async def create_agents(self, browser_manager: BrowserManager) -> Sequence[BaseAgent]:
        """
        Return the list of agents for this configuration.
        """
        pass

    async def run(
        self,
        task: str,
        base_url: str | None = None,
        task_id: str | None = None,
        record_video: bool = False,
        video_recorder: VideoRecorderService | None = None,
    ) -> AsyncIterator[Event]:
        """
        Spin up a browser, build this configuration's agents, and run the agent
        loop end-to-end, yielding Events as it progresses. The browser is closed
        automatically when the loop ends, errors out, or is cancelled - callers
        may also call shutdown() explicitly to close it earlier.

        Also sets up the same on-disk logging cli_main.py performs manually
        (browser-use logs, screenshots, a per-step context snapshot) under
        ./logs/, since BrowserAgent.decide() requires those storage keys to
        already be present - without them it raises a KeyError the moment it
        runs.
        """
        self._browser_manager = BrowserManager()
        await self._browser_manager.start()
        await self._browser_manager.get_browser()

        if base_url:
            await self._browser_manager.goto(base_url)

        log_dir = self._make_log_dir(task_id)
        logger.info("run start: config=%s task_id=%s log_dir=%s", self.__class__.__name__, task_id, log_dir)

        frame_stream = None
        frame_task = None
        try:
            agents = await self.create_agents(self._browser_manager)
            context = await self.setup_context(task=task, browser_manager=self._browser_manager)
            context["storage"]["screenshots_path"] = f"{log_dir}/screenshots"
            context["storage"]["logs_path"] = f"{log_dir}/logs.txt"
            context["storage"]["context_filename"] = f"{log_dir}/agent_context.json"
            context["storage"]["run_task_id"] = task_id
            screenshot_task_id = task_id.rsplit("_", 1)[0] if task_id else task_id
            task_screenshots = Path(__file__).resolve().parent.parent / "tasks" / screenshot_task_id / "screenshots"
            context["storage"]["screenshots_path"] = str(task_screenshots)
            context["storage"]["task_screenshots_id"] = screenshot_task_id
            task_screenshots.mkdir(parents=True, exist_ok=True)
            streaming_enabled = os.getenv("DEMO_BROWSER_STREAMING", "").strip().lower() in {
                "1", "true", "yes", "on",
            }
            if streaming_enabled and screenshot_task_id:
                frame_stream = get_browser_stream(screenshot_task_id)

            if (streaming_enabled or record_video) and screenshot_task_id:
                async def capture_frames() -> None:
                    consecutive_failures = 0
                    while True:
                        try:
                            frame = await asyncio.wait_for(
                                self._browser_manager.capture_jpeg(),
                                timeout=8,
                            )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            consecutive_failures += 1
                            should_log_error = consecutive_failures == 1 or consecutive_failures % 3 == 0
                            log = logger.error if should_log_error else logger.warning
                            log(
                                "Browser preview capture failed for task_id=%s "
                                "(consecutive failures=%d); retrying",
                                screenshot_task_id,
                                consecutive_failures,
                                exc_info=True,
                            )
                            await asyncio.sleep(min(0.5 * consecutive_failures, 5))
                        else:
                            if frame_stream is not None:
                                await frame_stream.publish(frame)
                            if record_video and video_recorder is not None:
                                encoded_frame = base64.b64encode(frame).decode("ascii")
                                await asyncio.to_thread(video_recorder.add_frame, encoded_frame)
                            if consecutive_failures:
                                logger.info(
                                    "Browser preview capture recovered for task_id=%s "
                                    "after %d consecutive failures",
                                    screenshot_task_id,
                                    consecutive_failures,
                                )
                            consecutive_failures = 0
                            await asyncio.sleep(0.2 if record_video else 0.5)

                frame_task = asyncio.create_task(capture_frames())
            internal_events: asyncio.Queue[Event | None] = asyncio.Queue()

            async def publish_internal_step(data: dict[str, Any]) -> None:
                await internal_events.put(Event(type="browser_internal_step", data=data))

            context["storage"]["publish_internal_step"] = publish_internal_step
            os.makedirs(context["storage"]["screenshots_path"], exist_ok=True)

            async def produce_events() -> None:
                async for event in run_agents_loop(
                    agents=agents,
                    context=context,
                    max_iterations=self.max_iterations,
                    stop_agent_name=self.stop_agent_name,
                ):
                    await internal_events.put(event)
                await internal_events.put(None)

            producer = asyncio.create_task(produce_events())
            try:
                while True:
                    event = await internal_events.get()
                    if event is None:
                        break
                    if event.type in ("step_complete", "stopped", "max_iterations"):
                        logger.info("run event: task_id=%s type=%s data=%s", task_id, event.type, event.data)
                    if event.type == "step_complete":
                        await asyncio.to_thread(self._persist_context, context)
                    if event.type in ("completed", "stopped", "max_iterations"):
                        self.last_statistics = self._statistics(context)
                    yield event
                await producer
            finally:
                if not producer.done():
                    producer.cancel()
                    await producer
        except Exception:
            logger.exception("run failed: config=%s task_id=%s", self.__class__.__name__, task_id)
            raise
        finally:
            if frame_task is not None:
                frame_task.cancel()
                try:
                    await frame_task
                except asyncio.CancelledError:
                    pass
            logger.info("run end: config=%s task_id=%s", self.__class__.__name__, task_id)
            await self.shutdown()

    async def shutdown(self):
        """Close the browser opened by run(), if any. Safe to call more than once."""
        if self._browser_manager is not None:
            await self._browser_manager.stop()
            self._browser_manager = None

    def _make_log_dir(self, task_id: str | None) -> str:
        time_stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
        suffix = f"_{task_id}" if task_id else ""
        log_dir = f"./logs/{self.__class__.__name__}_{time_stamp}{suffix}"
        os.makedirs(log_dir, exist_ok=True)
        return log_dir

    def _persist_context(self, context: AgentContext):
        with open(context["storage"]["context_filename"], "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _statistics(context: AgentContext) -> dict[str, Any]:
        usage = context["storage"].get("token_usage", [])
        decisions = context["storage"].get("agent_decisions", {})
        by_agent: dict[str, dict[str, int]] = {}
        for item in usage:
            agent = item.get("agent", "unknown")
            values = item.get("usage", {})
            current = by_agent.setdefault(
                agent,
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": decisions.get(agent, 0)},
            )
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                current[key] += int(values.get(key, 0) or 0)
        for agent, calls in decisions.items():
            by_agent.setdefault(agent, {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": calls,
            })
        total = {
            key: sum(agent.get(key, 0) for agent in by_agent.values())
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        return {
            "iterations": context["storage"].get("iterations", 0),
            "llm_calls": sum(decisions.values()),
            "tokens_by_agent": by_agent,
            "tokens_total": total,
        }

class BrowserOnlyConfiguration(AgentConfiguration):
    """
    Configuration with only the browser agent that gets the entire test as input
    """

    def __init__(self, llm: ModelConfiguration, num_task_executions: int, max_iterations: int, vision_enabled: bool = False):
        super().__init__(llm=llm, num_task_executions=num_task_executions, max_iterations=1, vision_enabled=vision_enabled)
        self.max_steps = max_iterations     # Browser-Use only, map the iterations to the steps in browser-use

    async def setup_context(self, task: str, browser_manager: BrowserManager) -> AgentContext:
        current_url = await browser_manager.get_URL()
        current_state = await browser_manager.get_stripped_DOM()

        task_message = textwrap.dedent(f"""
            Execute the following test case in Gherkin syntax on the provided web application:
            {task}

            Please execute it to the best of your abilities.
            """).strip()

        context: AgentContext = {
            "user_message": "",
            "task": task_message,
            "state": {
                "url": current_url,
                "simplified_dom": current_state,
                },
            "messages": [],
            "storage": {},
        }
        context["storage"].setdefault("action_history", [])
        context["storage"].setdefault("last_tool_calls", [])
        context["storage"].setdefault("iterations", 0)

        return context
        
    async def create_agents(self, browser_manager: BrowserManager) -> Sequence[BaseAgent]:


        # ----------------
        # OpenAI clients
        # ---------------- 
        llm = self.llm.connect_browser_llm()

        # ----------------
        # Agents
        # ----------------

        browser = await browser_manager.get_browser()
        browser_agent = BrowserAgent(
            agent_name="browser",
            browser_manager=browser_manager,
            browser=browser,
            llm=llm,
            max_actions_per_step=50,
            max_steps=self.max_steps,
            vision_enabled=self.vision_enabled,
        )
        

        return [
            browser_agent,
        ]

def observe_agent_task_prompt(context: dict) -> str:
    state = context.get("state", {})
    
    state_str = json.dumps(state, default=str, indent=2)

    judgement = context["storage"].get("latest_judgement", None)
    latest_success = context["storage"].get("latest_success", False)
    browser_result = (
        f"Success: {latest_success}"
        + (f"\nJudgement: {judgement}" if judgement else "")
    )

    prompt = f"""
The goal was to finsh the following test:
{context.get('task', '')}

Result of the browser execution:
{browser_result}

Current state (url and simplified DOM) after the most recent action was perfromed:
{state_str}

Based on this information, decide whether to call `stop` (if the test is complete or cannot proceed) 
or `continue` (if the test should retry or proceed). 
If using `continue`, provide a hint to guide the next attempt.
    """.strip()
    return prompt


class FourAgentConfiguration(AgentConfiguration):
    """
    Configuration with 4 agents in a shared conversational history mode:
    - analyst, coordinator, browser, observer
    Includes all standard tools.
    """

    stop_agent_name = "coordinator"

    def __init__(self, llm: ModelConfiguration, num_task_executions: int, max_iterations: int, vision_enabled: bool = False):
        super().__init__(llm=llm, num_task_executions=num_task_executions, max_iterations=max_iterations, vision_enabled=vision_enabled)

    async def setup_context(self, task: str, browser_manager: BrowserManager) -> AgentContext:
        current_url = await browser_manager.get_URL()
        current_state = await browser_manager.get_stripped_DOM()

        user_message = textwrap.dedent(f"""
            Execute the following test case in Gherkin syntax on the provided web application:
            {task}
            """).strip()

        context: AgentContext = {
            "user_message": user_message,
            "task": "",
            "state": {
                "url": current_url,
                "simplified_dom": current_state,
                },
            "messages": [],
            "storage": {},
        }
        context["storage"].setdefault("action_history", [])
        context["storage"].setdefault("iterations", 0)

        return context
        

    async def create_agents(self, browser_manager: BrowserManager) -> Sequence[BaseAgent]:
        # ----------------
        # Tools
        # ----------------

        tools = [
            GetCurrentURLTool(browser_manager=browser_manager),
            DomContainsTextTool(browser_manager=browser_manager),
            DomExistsSelectorTool(browser_manager=browser_manager),
            DomCountSelectorTool(browser_manager=browser_manager),
            DomGetTextTool(browser_manager=browser_manager),
            FindElementsByIdTool(browser_manager=browser_manager),
            FindElementsByIdHTMLTool(browser_manager=browser_manager),
            GetAllIdsTool(browser_manager=browser_manager),
        ]

        # ----------------
        # OpenAI clients
        # ----------------

        openai_client = self.llm.connect_generic_llm()
        llm = self.llm.connect_browser_llm()

        # ----------------
        # Agents
        # ----------------

        analyst = CompletionAgent(
            agent_name="analyst",
            system_prompt=textwrap.dedent("""
                You are the Analyst agent in a multi-agent web testing system.

                Your responsibility is to analyze the current web application state and the overall test goal, and decide what the next step in the test should be.

                Rules:
                - Focus on reasoning about test progress and identifying the next logical intent.
                - Base your analysis strictly on the provided page state and test description.
                - If the state is ambiguous or missing information, explicitly say what is unclear.
                - You may call tools if provided to get more context about the web application's current state.
                - Call tools ONLY if the state is ambiguous. Do not re-verify after initial check.
                - For forms please provide all inputs for the next action at once.
                - If for some forms not all inputs are given in the task description you may randomly generate inputs that make sense.
                - Do never change the given values, but you may adjust the randomly generate inputs if they do not work.


                Output format (always):
                1. Current test objective:
                2. Observed state summary:
                3. Next action to perform:
                """).strip(),
            client=openai_client,
            model=self.llm.model,
            tools=None,
            max_tool_calls=1
        )

        # create special tools dictionary
        special_tools = {
            PerformActionTool(): handle_perform_action,
            StopTool(): handle_stop,
        }

        coordinator = ToolAgent(
            agent_name="coordinator",
            system_prompt=textwrap.dedent("""
                You are the Coordinator agent in a multi-agent web testing system.

                Your responsibility is to convert the Analyst's high-level intent into a single precise executable UI action using the available tools.

                Rules:
                - You MUST produce exactly one atomic action per turn. To fill forms you should pass all available inputs in one action.
                - You MUST give all the concrete inputs to fill form with.
                - The action must be directly grounded in the current page state (visible elements only).
                - If multiple elements have the same label or other identifiers, be specific about which one you mean, for instance by passing their Index.
                - Do NOT guess element names or IDs—only use selectors or labels that appear in the given state.
                - Do NOT perform analysis of the whole test plan; only focus on the next action.
                - You may call other tools if provided to get more context.
                - For your decision call tools `perform_action` (to execute ONE browser action) or `stop` (if the task is complete or cannot proceed).
                - You should try to complete the task and only stop when you are sure the task was completed or all possible actions to try to complete the task have been exhausted. 
                - Use the current page-state provided to you, to identify elements and indizes.
            """).strip(),
            client=openai_client,
            model=self.llm.model,
            tools=tools,
            special_tool_handlers=special_tools,
        )

        observer = CompletionAgent(
            agent_name="observer",
            system_prompt=textwrap.dedent("""
                You are the Observer agent in a multi-agent web testing system.

                Your responsibility is to monitor whether the test execution is still consistent with the intended test scenario.

                Rules:
                - Do NOT suggest new actions or interact with tools.
                - Evaluate the latest state against the overall test goal and expected progress.
                - Detect deviations such as wrong page, missing elements, unexpected popups, or failed transitions.
                - If execution is correct, confirm briefly.
                - If execution is off track, clearly describe the issue and what needs to be corrected at a high level.

                Output format (always):
                Status: ON_TRACK or OFF_TRACK
                Reason:
                Expected vs Observed:
                Recommended adjustment (high-level only):
                                          
                Example output:
                Status: OFF_TRACK
                Reason: Login failed; still on login page with error message.
                Expected vs Observed: Expected dashboard, observed invalid password alert.
                Recommended adjustment: Re-attempt login with correct credentials.
                """).strip(),
            client=openai_client,
            model=self.llm.model,
            tools=None,
        )

        browser = await browser_manager.get_browser()
        browser_agent = BrowserAgent(
            agent_name="browser",
            browser_manager=browser_manager,
            browser=browser,
            llm=llm,
            max_actions_per_step=10,
            max_steps=10,
            stop_on_completion=False,
        )

        return [
            analyst,
            coordinator,
            browser_agent,
            observer,
        ]

def analyst_task_prompt(context: dict) -> str:
    state = context.get("state", {})
    last_tool_calls = context["storage"].get("last_tool_calls", [])
    action_history = context["storage"].get("action_history", [])
    user_message = context.get("user_message", "")

    state_str = json.dumps(state, default=str, indent=2)

    observer_message = ""
    iterations = context["storage"].get("iterations", 0)
    if iterations > 0:
        # Find the last message from the observer
        for msg in reversed(context["messages"]):
            if msg.get("role") == "assistant" and msg.get("name") == "observer":
                observer_message = msg.get("content", "")
                break

    observer_feedback = f"Observer feedback:\n{observer_message}" if observer_message else ""
    prompt = f"""
User task description:
{user_message}

Current state (url and simplified DOM):
{state_str}

Previous actions taken:
{action_history}

Last tool calls:
{last_tool_calls}

{observer_feedback}

Please provide your analysis of the current test progress and decide the next high-level action.

Output format:
1. Current test objective:
2. Observed state summary:
3. Next action to perform:
    """.strip()
    return prompt

def coordinator_task_prompt(context: dict) -> str:
    state = context.get("state", {})
    last_tool_calls = context["storage"].get("last_tool_calls", [])
    action_history = context["storage"].get("action_history", [])

    state_str = json.dumps(state, default=str, indent=2)

    analyst_message = ""
    # Find the last message from the analyst
    for msg in reversed(context["messages"]):
        if msg.get("role") == "assistant" and msg.get("name") == "analyst":
            analyst_message = msg.get("content", "")
            break

    prompt = f"""
Analyst intent:
{analyst_message}

Current state (url and simplified DOM):
{state_str}

Action history:
{action_history}

Last tool calls:
{last_tool_calls}

Based on the analyst's intent and current state, produce **exactly one atomic browser action**.
Call tool `perform_action` to perfrom an action or tool `stop` when the test exectuion is finished accordingly.
    """.strip()
    return prompt

def observer_task_prompt(context: dict) -> str:
    test_goal = context.get("task", "")
    state = context.get("state", {})
    last_action = context["storage"].get("action_history", [])[-1:]  # only last action
    
    state_str = json.dumps(state, default=str, indent=2)

    judgement = context["storage"].get("latest_judgement", None)
    latest_success = context["storage"].get("latest_success", False)
    browser_result = (
        f"Success: {latest_success}"
        + (f"\nJudgement: {judgement}" if judgement else "")
    )

    prompt = f"""
Original test goal:
{test_goal}

Most recent action taken:
{last_action}

Result of the last browser execution:
{browser_result}

Current state (url and simplified DOM) after the most recent action was perfromed:
{state_str}

Evaluate whether the latest execution is consistent with the original test goal.
Use the test goal as the source of expected behavior; do not infer requirements
from another agent's analysis or recommendations.
Output format (always):
Status: ON_TRACK or OFF_TRACK
Reason:
Expected vs Observed:
Recommended adjustment (high-level only):
    """.strip()
    return prompt


# NOTE: Did some initial tests with this but it performed horribly. Kept repeating steps in simple tests, bould not figure out simple steps and would not fail tests.
class FourAgentConfiguration_STATE(AgentConfiguration):
    """
    Configuration with 4 agents in a individual LLM call with state mode:
    - analyst, coordinator, browser, observer
    Includes all standard tools.
    """

    stop_agent_name = "coordinator"

    def __init__(self, llm: ModelConfiguration, num_task_executions: int, max_iterations: int, vision_enabled: bool = False):
        super().__init__(llm=llm, num_task_executions=num_task_executions, max_iterations=max_iterations, vision_enabled=vision_enabled)

    async def setup_context(self, task: str, browser_manager: BrowserManager) -> AgentContext:
        current_url = await browser_manager.get_URL()
        current_state = await browser_manager.get_stripped_DOM()

        user_message = textwrap.dedent(f"""
            Execute the following test case in Gherkin syntax on the provided web application:
            {task}

            Current url: {current_url}
            
            Current page state: {current_state}
            """).strip()

        context: AgentContext = {
            "user_message": user_message,
            "task": task,
            "state": {
                "url": current_url,
                "simplified_dom": current_state,
                },
            "messages": [],
            "storage": {},
        }
        context["storage"].setdefault("action_history", [])
        context["storage"].setdefault("iterations", 0)
        context["storage"].setdefault("last_tool_calls", [])

        return context
        

    async def create_agents(self, browser_manager: BrowserManager) -> Sequence[BaseAgent]:
        # ----------------
        # Tools
        # ----------------

        tools = [
            # GetCurrentURLTool(browser_manager=browser_manager),
            # DomContainsTextTool(browser_manager=browser_manager),
            # DomExistsSelectorTool(browser_manager=browser_manager),
            # DomCountSelectorTool(browser_manager=browser_manager),
            # DomGetTextTool(browser_manager=browser_manager),
            FindElementsByIdTool(browser_manager=browser_manager),
            FindElementsByIdHTMLTool(browser_manager=browser_manager),
            GetAllIdsTool(browser_manager=browser_manager),
        ]

        # ----------------
        # OpenAI clients
        # ----------------

        openai_client = self.llm.connect_generic_llm()
        llm = self.llm.connect_browser_llm()

        # ----------------
        # Agents
        # ----------------

        analyst = CompletionAgent(
            agent_name="analyst",
            system_prompt=textwrap.dedent("""
                You are the Analyst agent in a multi-agent web testing system.

                Your responsibility is to analyze the current web application state and the overall test goal, and decide what the next step in the test should be.
                The goal is to test the application not to complete the task by any means, so if a test cannot be finished it should be failed.

                Rules:
                - Focus on reasoning about test progress and identifying the next logical intent.
                - Base your analysis strictly on the provided state and test description.
                - If the state is ambiguous or missing information, explicitly say what is unclear.
                - You may call tools if provided to get more context about the web application's current state.
                - For forms please provide all inputs for the next action at once.
                - If for some forms not all inputs are given in the task description you may randomly generate inputs that make sense.
                - Do never change the given values, but you may adjust the randomly generate inputs if they do not work.
                - If the test was executed completely the next action to perform should be to stop with the fitting verdict.
                - If the test failed the execution should be stopped with the appropriate verdict and reason.
                - If you have tried to finish the test multiple times already, but cannot succeed the next action should be to fail the test.

                Output format (always):
                1. Current test objective:
                2. Observed state summary:
                3. Next action to perform:
                """).strip(),
            client=openai_client,
            model=self.llm.model,
            tools=tools,
            interaction_mode=InteractionMode.STATE_BASED,
            task_prompt_fn=analyst_task_prompt,
        )

        # create special tools dictionary
        special_tools = {
            PerformActionTool(): handle_perform_action,
            StopTool(): handle_stop,
        }

        coordinator = ToolAgent(
            agent_name="coordinator",
            system_prompt=textwrap.dedent("""
                You are the Coordinator agent in a multi-agent web testing system.

                Your responsibility is to convert the Analyst's high-level intent into a single precise executable UI action using the available tools.

                Rules:
                - You MUST produce exactly one atomic action per turn. To fill forms you should pass all available inputs in one action.
                - You MUST give all the concrete inputs to fill form with.
                - The action must be directly grounded in the current page state (visible elements only).
                - If multiple elements have the same label or other identifiers, be specific about which one you mean, for instance by passing their Index.
                - Do NOT guess element names or IDs—only use selectors or labels that appear in the given state.
                - Do NOT perform analysis of the whole test plan; only focus on the next action.
                - You may call other tools if provided to get more context.
                - For your decision call tools `perform_action` (to execute ONE browser action) or `stop` (if the task is complete or cannot proceed).
                - You should try to complete the task and only stop when you are sure the task was completed or all possible actions to try to complete the task have been exhausted. 
                """).strip(),
            client=openai_client,
            model=self.llm.model,
            tools=tools,
            special_tool_handlers=special_tools,
            interaction_mode=InteractionMode.STATE_BASED,
            task_prompt_fn=coordinator_task_prompt,
        )

        observer = CompletionAgent(
            agent_name="observer",
            system_prompt=textwrap.dedent("""
                You are the Observer agent in a multi-agent web testing system.

                Your responsibility is to monitor whether the test execution is still consistent with the intended test scenario.

                Rules:
                - Do NOT suggest new actions or interact with tools.
                - Evaluate the latest state against the overall test goal and expected progress.
                - Detect deviations such as wrong page, missing elements, unexpected popups, or failed transitions.
                - If execution is correct, confirm briefly.
                - If execution is off track, clearly describe the issue and what needs to be corrected at a high level.

                Output format (always):
                Status: ON_TRACK or OFF_TRACK
                Reason:
                Expected vs Observed:
                Recommended adjustment (high-level only):
                                          
                Example output:
                Status: OFF_TRACK
                Reason: Login failed; still on login page with error message.
                Expected vs Observed: Expected dashboard, observed invalid password alert.
                Recommended adjustment: Re-attempt login with correct credentials.
                """).strip(),
            client=openai_client,
            model=self.llm.model,
            tools=tools,
            interaction_mode=InteractionMode.STATE_BASED,
            task_prompt_fn=observer_task_prompt,
        )

        browser = await browser_manager.get_browser()
        browser_agent = BrowserAgent(
            agent_name="browser",
            browser_manager=browser_manager,
            browser=browser,
            llm=llm,
            max_actions_per_step=10,
            max_steps=self.max_iterations,
            vision_enabled=self.vision_enabled,
            stop_on_completion=False,
        )

        return [
            analyst,
            coordinator,
            browser_agent,
            observer,
        ]