import json
import textwrap
import logging
import asyncio

from typing import TypedDict, Literal, Any, Optional, Callable, Awaitable, NotRequired, cast
from abc import ABC, abstractmethod
from typing import Sequence
from enum import Enum

from agents.browser_manager import BrowserManager

from browser_use import Browser, Agent 
from browser_use.llm.base import BaseChatModel
from browser_use.agent.views import AgentHistoryList, Path

from openai import NOT_GIVEN, AsyncOpenAI, BadRequestError
from openai.types.chat.chat_completion_message import ChatCompletionMessage
from openai.types.chat import ChatCompletionMessageParam, ChatCompletionAssistantMessageParam, ChatCompletionMessageToolCall, ChatCompletionToolMessageParam

from agents.tools import Tool

logger = logging.getLogger(__name__)


class AgentDecision(TypedDict):
    type: Literal["continue", "stop"]
    payload: Optional[str | dict[str, Any]]

class AgentContext(TypedDict):
    user_message: str
    task: str
    state: dict[str, Any]
    messages: list[ChatCompletionMessageParam]
    storage: dict[str, Any]

SpecialToolHandler = Callable[[dict[str, Any], AgentContext, list[ChatCompletionMessageParam], str], Awaitable[Optional[AgentDecision]]]

class InteractionMode(Enum):
    SHARED_HISTORY = "shared_history" # conversational cooperation mode
    STATE_BASED = "state_based" # individual LLM calls with the current state

class BaseAgent(ABC):
    """
    Base interface for all LLM-based agents.
    """

    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        tools: Sequence[Tool] | None = None,
        interaction_mode: InteractionMode = InteractionMode.SHARED_HISTORY,
        task_prompt_fn: Callable[[AgentContext], str] | None = None,
    ):
        self.tools = tools or []
        self.system_prompt = system_prompt
        self.agent_name = agent_name
        self.interaction_mode = interaction_mode
        self.task_prompt_fn = task_prompt_fn

        if (
            interaction_mode is InteractionMode.STATE_BASED
            and task_prompt_fn is None
        ):
            raise ValueError("STATE_BASED mode requires task_prompt_fn")

    @abstractmethod
    async def decide(
        self,
        context: AgentContext,
    ) -> AgentDecision:
        """
        Makes one decision:
        - request a tool
        - return an action
        - stop
        """
        pass

    # ----------------
    # Tool schema
    # ----------------

    def _openai_tools(self, include_tools: list[str] | None = None) -> list[dict] | None:
        if not self.tools:
            return None

         # filter tools if include_tools is given
        tools_to_use = self.tools
        if include_tools is not None:
            tools_to_use = [tool for tool in self.tools if tool.name in include_tools]

        if not tools_to_use:
            return None

        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools_to_use
        ]
    
    async def call_llm(
        self,
        client: AsyncOpenAI,
        model: str,
        temperature: float,
        context: AgentContext,
        messages: list[ChatCompletionMessageParam],
        required_tools: bool = False,
        allowed_tools: list[str] | None = None,
    ) -> ChatCompletionMessage | None:
        
        try:
            tools_to_pass = self._openai_tools(include_tools=allowed_tools) if self.tools else None
            tool_choice = (
                "required" if required_tools else "auto"
            ) if tools_to_pass else NOT_GIVEN

            # with open("llm_calls.log", "a", encoding="utf-8") as f:
            #     f.write(f"==================================================================================\n")
            #     f.write(f"==================================================================================\n")
            #     f.write(f"== CALLING LLM: {self.agent_name} ==\n")
            #     f.write(json.dumps(messages, indent=2, default=str))
            #     f.write("\n\n")

            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                tools=tools_to_pass,
                tool_choice=tool_choice,
                timeout=60,  # seconds
            )

            usage_dict = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            context["storage"].setdefault("token_usage", []).append({
                "agent": self.agent_name,
                "usage": usage_dict,
            })

            message = response.choices[0].message
            return message
        except BadRequestError as e:
            print(f"[LLM Error] Bad request: {e}")
        except Exception as e:
            print(f"[LLM Error] Unexpected: {e}")

    def build_messages(self, context: AgentContext) -> list[ChatCompletionMessageParam]:
        if self.interaction_mode is InteractionMode.SHARED_HISTORY:
            return self._build_shared_history_messages(context)

        return self._build_state_based_messages(context)

    def _build_shared_history_messages(self, context: AgentContext) -> list[ChatCompletionMessageParam]:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context['user_message']},
        ]
        state = context.get("state")
        if state:
            messages.append({
                "role": "user",
                "content": f"Current page state:\n{json.dumps(state, indent=2, default=str)}"
            })

        messages.extend(context["messages"])
        return messages

    def _build_state_based_messages(self, context: AgentContext) -> list[ChatCompletionMessageParam]:
        user = {
            "role": "user",
            "content": self.task_prompt_fn(context),
        }
        context["messages"].append(user)

        return [
            {"role": "system", "content": self.system_prompt},
            user,
        ]

    async def decide_generic(
        self,
        client: AsyncOpenAI,
        model: str,
        temperature: float,
        context: AgentContext,
        required_tools: bool = False,
        max_tool_calls: int = 10,
        special_tool_handlers: dict[str, SpecialToolHandler] | None = None,
    ) -> AgentDecision:
        context["storage"].setdefault("last_tool_calls", [])
        context["storage"]["last_tool_calls"] = []

        messages = self.build_messages(context)

        special_tool_handlers = special_tool_handlers or {}

        allowed_tools = None
        tool_calls = 0
        empty_response_retries = 0
        while True:
            if tool_calls >= max_tool_calls:
                if required_tools and special_tool_handlers:
                    allowed_tools = list(special_tool_handlers.keys())  # only allow special tools
                else:
                    allowed_tools = []  # no tools allowed anymore

            message = await self.call_llm(
                client=client,
                model=model,
                messages=messages,
                temperature=temperature,
                context=context,
                required_tools=required_tools,
                allowed_tools=allowed_tools,
            )

            if not message:
                return AgentDecision(type="stop", payload="No message returned from LLM call")

            # ---- No tool call
            if not message.tool_calls:
                if required_tools:
                    return AgentDecision(type="stop", payload="Expected a tool call but none was produced")

                # Normal response
                content = self._extract_message_content(message)
                if not content:
                    if empty_response_retries == 0:
                        empty_response_retries += 1
                        messages.append({
                            "role": "user",
                            "content": (
                                "Return a concise plain-text response now. Do not leave the "
                                "response empty and do not call a tool."
                            ),
                        })
                        continue
                    refusal = getattr(message, "refusal", None)
                    logger.warning(
                        "Agent '%s' returned an empty response (refusal=%r, reasoning=%r, finish_reason=%r)",
                        self.agent_name,
                        refusal,
                        self._message_extra(message, "reasoning_content"),
                        getattr(message, "finish_reason", None),
                    )
                    content = "The model returned no usable text or tool call."
                context["messages"].append({
                    "role": "assistant", 
                    "content": content, 
                    "name": self.agent_name,
                })

                return AgentDecision(type="continue", payload=content)

            # ---- Tool call exists 
            assistant_message = cast(
                ChatCompletionAssistantMessageParam,
                message.model_dump(exclude_unset=True)
            )
            assistant_message["name"] = self.agent_name

            messages.append(assistant_message)
            context["messages"].append(assistant_message)

            # ---- Tool call(s) exist
            for tool_call in message.tool_calls:
                assert isinstance(tool_call, ChatCompletionMessageToolCall)
                tool_name = tool_call.function.name
                args_str = tool_call.function.arguments
                args = json.loads(args_str)

                if tool_name in special_tool_handlers:
                    # ignore any other tool calls in the same message
                    decision = await special_tool_handlers[tool_call.function.name](args, context, messages, tool_call.id)
                    if decision:
                        # Append stub results for any remaining tool calls that won't be processed,
                        # so the message history stays valid for other agents using shared context.
                        remaining = message.tool_calls[message.tool_calls.index(tool_call) + 1:]
                        for remaining_call in remaining:
                            stub = ChatCompletionToolMessageParam(
                                role="tool",
                                content="IGNORED: You called multiple special tools in one response. Only the first was executed. You must call exactly one special tool per response.",
                                tool_call_id=remaining_call.id,
                            )
                            context["messages"].append(stub)
                            messages.append(stub)

                        return decision
                    break  # stop processing remaining tool calls  

                

                tool_to_call = next((t for t in self.tools if t.name == tool_name), None)
                if not tool_to_call:
                    logger.warning("Unknown tool '%s' called by agent '%s'", tool_name, self.agent_name)
                    return AgentDecision(type="stop", payload=f"Unknown tool: {tool_name}")
                
                tool_result = await tool_to_call.run(json.loads(args_str))
                tool_calls += 1

                tool_message = ChatCompletionToolMessageParam(
                    role="tool", 
                    content=f"{tool_result}",
                    tool_call_id=tool_call.id,
                )
                context["messages"].append(tool_message)

                if self.interaction_mode is InteractionMode.SHARED_HISTORY:
                    messages.append(tool_message)
                elif self.interaction_mode is InteractionMode.STATE_BASED:
                    messages = self.build_messages(context)

                context["storage"].setdefault("last_tool_calls", []).append({
                    "name": tool_name,
                    "arguments": args_str,
                    "result": f"{tool_result}",
                })

    @staticmethod
    def _message_extra(message: ChatCompletionMessage, key: str) -> Any:
        """Read provider-specific fields returned outside the OpenAI schema."""
        extra = getattr(message, "model_extra", None) or {}
        return extra.get(key)

    @classmethod
    def _extract_message_content(cls, message: ChatCompletionMessage) -> str:
        content = message.content
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            if parts:
                return "\n".join(part.strip() for part in parts if part.strip())

        reasoning = cls._message_extra(message, "reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            logger.info(
                "Using provider reasoning_content as fallback text for agent '%s'",
                getattr(message, "name", "unknown"),
            )
            return reasoning.strip()
        return ""

def set_browser_use_log_file(logger: logging.Logger, filename: str):
    """Redirect all browser-use logs to a specific file."""
    root_logger = logging.getLogger('browser_use')

    # remove old file handlers from both loggers
    for log in [logger, root_logger]:
        for handler in list(log.handlers):
            if isinstance(handler, logging.FileHandler):
                log.removeHandler(handler)
                handler.close()

    # create and add a new file handler to both
    file_handler = logging.FileHandler(filename, mode="a", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    root_logger.addHandler(file_handler)


class BrowserStepLogHandler(logging.Handler):
    """Forward browser-use's concise progress lines to the task event stream."""

    _prefixes = (
        "📍 Step",
        "❔ Eval:",
        "🧠 Memory:",
        "🎯 Next goal:",
        "▶️",
        "📋 Plan updated",
        "📄 Final Result:",
        "✅ Task completed",
        "❌ Task failed",
    )

    def __init__(self, loop: asyncio.AbstractEventLoop, publish, outer_step: int, agent_name: str):
        super().__init__()
        self.loop = loop
        self.publish = publish
        self.outer_step = outer_step
        self.agent_name = agent_name
        self.internal_step = 0

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage().strip()
        if not message or not message.startswith(self._prefixes):
            return
        if message.startswith("📍 Step"):
            try:
                self.internal_step = int(message.split("Step", 1)[1].split(":", 1)[0].strip())
            except (IndexError, ValueError):
                pass
        data = {
            "agent": self.agent_name,
            "step": self.outer_step,
            "call_id": f"{self.outer_step}:{self.agent_name}",
            "internal_step": self.internal_step,
            "kind": "browser_use_log",
            "text": message,
        }
        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.publish(data))
        )


class BrowserAgent(BaseAgent):
    """
    A BrowserAgent that executes actions in a browser-use agent.
    """

    def __init__(
        self,
        *,
        agent_name: str,
        browser_manager: BrowserManager,
        browser: Browser,
        llm: BaseChatModel,
        tools: Sequence[Tool] | None = None,
        max_actions_per_step: int = 10,
        max_steps: int = 500,
        vision_enabled: bool = False,
        stop_on_completion: bool = True,

    ):
        super().__init__(agent_name=agent_name, system_prompt=None, tools=tools)
        self.browser_manager = browser_manager
        self.browser = browser
        self.llm = llm
        self.max_actions_per_step = max_actions_per_step
        self.max_steps = max_steps
        self.vision_enabled = vision_enabled
        self.stop_on_completion = stop_on_completion

        # Internal stop flag
        self._stop_state = {"stop": False}
        self._screenshots_path = ""
        self._step = 0
        self._event_sink = None

    def task_prompt(self, context: AgentContext) -> str:
        return textwrap.dedent(f"""
            Only perform the task you are given.

            TASK: {context['task']}

            After you are done with this task you can stop and give up control of the browser.
            Do not perform any tasks beyond what you where asked to do.
        """).strip()

    # ----------------
    # Step callback for the agent
    # ----------------

    async def _step_callback(self, browser_state, agent_output, step_index):
        print(f"[BrowserAgent] Step {step_index}: last action = {getattr(agent_output, 'actions', None)}")
        filename = f"step_{self._step}_{step_index}.png"
        await self.browser_manager.screenshot(f"{self._screenshots_path}/{filename}")
        publish = self._event_sink
        if publish:
            await publish({
                "agent": self.agent_name,
                "step": self._step,
                "call_id": f"{self._step}:{self.agent_name}",
                "internal_step": step_index,
                "kind": "screenshot",
                "screenshot": {
                    "filename": filename,
                    "task_id": self._run_task_id,
                    "url": f"/api/tasks/{self._run_task_id}/screenshots/{filename}",
                },
            })

        # Stop after a fixed number of steps or implement more complex logic
        if step_index >= self.max_actions_per_step:
            self._stop_state["stop"] = True

    async def _should_stop(self) -> bool:
        return self._stop_state["stop"]

    # ----------------
    # Decision logic
    # ----------------

    async def decide(self, context: AgentContext) -> AgentDecision:
        """
        Execute the browser action described in context['task'].
        Stops automatically when the action is done or max steps exceeded.
        Returns the final action result as payload.
        """
        self._stop_state["stop"] = False

        task = self.task_prompt(context)

        self._screenshots_path = context["storage"]["screenshots_path"] if context["storage"]["screenshots_path"] else "."
        self._step = context["storage"]["iterations"] if context["storage"]["iterations"] else 0
        self._event_sink = context["storage"].get("publish_internal_step")
        self._run_task_id = context["storage"].get("task_screenshots_id")

        agent = Agent(
            task=task,
            browser=self.browser,
            llm=self.llm,
            max_actions_per_step=self.max_actions_per_step,
            max_failures=1,
            register_new_step_callback=self._step_callback,
            register_should_stop_callback=self._should_stop,
            use_vision = self.vision_enabled,
        )
        
        if context["storage"]["logs_path"]:
            set_browser_use_log_file(agent.logger, context["storage"]["logs_path"])
        log_handler = BrowserStepLogHandler(
            asyncio.get_running_loop(),
            self._event_sink,
            self._step,
            self.agent_name,
        )
        logging.getLogger("browser_use").addHandler(log_handler)
        try:
            history: AgentHistoryList = await agent.run(max_steps=self.max_steps)
        finally:
            logging.getLogger("browser_use").removeHandler(log_handler)

        usage_dict = {
            "prompt_tokens": history.usage.total_prompt_tokens,
            "completion_tokens": history.usage.total_completion_tokens,
            "total_tokens": history.usage.total_tokens,
        }
        context["storage"].setdefault("token_usage", []).append({
            "agent": self.agent_name,
            "usage": usage_dict,
        })

        latest_result = history.history[-1].result[-1]

        # extracted_content is already the human-readable summary browser-use
        # produces for a result; falling back to str(item) only for the rare
        # case a result carries no summary at all.
        history_str = "\n".join(
            (item.extracted_content or str(item)) for item in history.history[-1].result
        )

        context["storage"]["latest_success"] = bool(latest_result.is_done and latest_result.success)
        context["storage"]["test_passed"] = context["storage"]["latest_success"]
        if latest_result.judgement is not None:
            try:
                context["storage"]["latest_judgement"] = json.dumps(latest_result.judgement, default=str, indent=2)
            except Exception:
                context["storage"]["latest_judgement"] = None
        else:
            context["storage"]["latest_judgement"] = None

        current_state = await self.browser.get_state_as_text()
        url = await self.browser.get_current_page_url() 
        context["state"] = {
            "url": url,
            "simplified_dom": current_state,
        }

        state_str = json.dumps(context["state"], default=str, indent=2)
        message_context=textwrap.dedent(f"""
                Execution result: {history_str},

                Current state: {state_str} 
                """).strip()

        context["messages"].append({
            "role": "assistant", 
            "content": message_context,
            "name": self.agent_name,
        })

        return AgentDecision(
            type="stop" if self.stop_on_completion and latest_result.is_done else "continue",
            payload=history_str,
        )

class CompletionAgent(BaseAgent):
    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        client: AsyncOpenAI,
        model: str,
        temperature: float = 0.2,
        tools: Sequence[Tool] | None = None,
        interaction_mode: InteractionMode = InteractionMode.SHARED_HISTORY,
        task_prompt_fn: Callable[[AgentContext], str] | None = None,
        max_tool_calls: int = 10,
    ):
        super().__init__(
            agent_name=agent_name,
            system_prompt=system_prompt,
            tools=tools,
            interaction_mode=interaction_mode, 
            task_prompt_fn=task_prompt_fn
        )
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tool_calls = max_tool_calls

    async def decide(self, context: AgentContext) -> AgentDecision:
        return await self.decide_generic(
            client=self.client,
            model=self.model,
            temperature=self.temperature,
            context=context,
            required_tools=False,
            max_tool_calls=self.max_tool_calls
        )

class ToolAgent(BaseAgent):
    def __init__(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        client: AsyncOpenAI,
        model: str,
        temperature: float = 0.2,
        tools: list[Tool] | None = None,
        special_tool_handlers: dict[Tool, SpecialToolHandler] | None = None,
        interaction_mode: InteractionMode = InteractionMode.SHARED_HISTORY,
        task_prompt_fn: Callable[[AgentContext], str] | None = None,
    ):
        # merge special tools with provided tools
        merged_tools = [*special_tool_handlers.keys()] if special_tool_handlers else []
        merged_tools.extend(tools or [])

        super().__init__(
            agent_name=agent_name, 
            system_prompt=system_prompt, 
            tools=merged_tools, 
            interaction_mode=interaction_mode, 
            task_prompt_fn=task_prompt_fn
        )
        self.client = client
        self.model = model
        self.temperature = temperature

        # map tool names to handlers
        self.special_tool_handlers = {tool.name: handler for tool, handler in (special_tool_handlers or {}).items()}

    async def decide(self, context: AgentContext) -> AgentDecision:
        return await self.decide_generic(
            client=self.client,
            model=self.model,
            temperature=self.temperature,
            context=context,
            required_tools=True,
            special_tool_handlers=self.special_tool_handlers,
        )
