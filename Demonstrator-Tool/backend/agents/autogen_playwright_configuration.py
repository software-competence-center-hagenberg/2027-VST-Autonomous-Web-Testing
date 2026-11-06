"""AutoGen configuration using generated Playwright scripts.

This runner is intentionally separate from the browser-use configurations.
AutoGen's executor runs generated scripts locally and those scripts connect to
the runner-owned Chromium instance through CDP.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, AsyncIterator

from browser_stream import BrowserFrameStream, get_browser_stream
from events import Event

logger = logging.getLogger(__name__)


class AutoGenPlaywrightConfiguration:
    """Run the legacy coordinator/coder/executor/analyst workflow."""

    def __init__(
        self,
        llm: Any,
        num_task_executions: int,
        max_iterations: int,
        vision_enabled: bool = False,
    ) -> None:
        self.llm = llm
        self.num_task_executions = num_task_executions
        self.max_iterations = max_iterations
        self.vision_enabled = vision_enabled
        self.last_statistics: dict[str, Any] = {}
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Request cancellation of the synchronous AutoGen worker."""
        self._cancel_event.set()

    async def run(
        self,
        task: str,
        base_url: str | None = None,
        task_id: str | None = None,
        record_video: bool = False,
        video_recorder: Any | None = None,
    ) -> AsyncIterator[Event]:
        if record_video and video_recorder is None:
            raise ValueError("A video recorder is required when record_video is enabled")

        started = time.monotonic()
        self._cancel_event.clear()
        self.last_statistics = {}
        streaming_enabled = self._env_enabled("DEMO_BROWSER_STREAMING")
        screenshot_task_id = task_id.rsplit("_", 1)[0] if task_id else task_id
        frame_stream = (
            get_browser_stream(screenshot_task_id)
            if streaming_enabled and screenshot_task_id
            else None
        )
        event_loop = asyncio.get_running_loop()
        state: dict[str, Any] = {"groupchat": None}
        worker = asyncio.create_task(
            asyncio.to_thread(
                self._run_sync,
                task,
                base_url,
                task_id,
                state,
                record_video,
                video_recorder,
                frame_stream,
                event_loop,
            )
        )
        seen_messages = 0
        current_step = 0
        try:
            while not worker.done():
                groupchat = state.get("groupchat")
                messages = list(getattr(groupchat, "messages", [])) if groupchat else []
                for message in messages[seen_messages:]:
                    seen_messages += 1
                    step = ((seen_messages - 1) // 4) + 1
                    agent = message.get("name", "autogen")
                    content = self._message_text(message.get("content"))
                    if step != current_step:
                        if current_step:
                            yield Event("step_complete", {"step": current_step})
                        current_step = step
                        yield Event("step_start", {"step": step})
                    yield Event(
                        "agent_decision",
                        {
                            "step": step,
                            "agent": agent,
                            "payload": content,
                            "message": content,
                        },
                    )
                await asyncio.sleep(0.25)
            result = await worker
        except asyncio.CancelledError:
            self.cancel()
            raise
        except Exception as exc:
            yield Event("error", {"message": str(exc)})
            return

        transcript = result["transcript"]
        message = result["message"]
        passed = result["passed"]
        self.last_statistics = result["statistics"]
        for raw_message in transcript[seen_messages:]:
            seen_messages += 1
            step = ((seen_messages - 1) // 4) + 1
            agent = raw_message.get("name", "autogen")
            content = self._message_text(raw_message.get("content"))
            if step != current_step:
                if current_step:
                    yield Event("step_complete", {"step": current_step})
                current_step = step
                yield Event("step_start", {"step": step})
            yield Event(
                "agent_decision",
                {"step": step, "agent": agent, "payload": content, "message": content},
            )
        if seen_messages == 0:
            yield Event("step_start", {"step": 1, "agent": "autogen"})
            yield Event(
                "agent_decision",
                {
                    "step": 1,
                    "agent": "autogen",
                    "payload": message,
                    "message": message,
                    "transcript": transcript,
                    "duration_seconds": round(time.monotonic() - started, 2),
                },
            )
            yield Event("step_complete", {"step": 1, "agent": "autogen"})
        elif current_step:
            yield Event("step_complete", {"step": current_step})
        if passed:
            yield Event("completed", {"message": message, "passed": True})
        elif result["max_iterations"]:
            yield Event(
                "max_iterations",
                {"step": seen_messages, "message": message},
            )
        else:
            yield Event("stopped", {"message": message, "passed": False})

    def _run_sync(
        self,
        task: str,
        base_url: str | None,
        task_id: str | None,
        state: dict[str, Any],
        record_video: bool,
        video_recorder: Any | None,
        frame_stream: BrowserFrameStream | None,
        event_loop: asyncio.AbstractEventLoop,
    ) -> dict[str, Any]:
        try:
            import autogen
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "AutoGen Playwright configuration requires pyautogen and playwright. "
                "Run 'uv sync --extra autogen --python 3.12' and "
                "'uv run playwright install chromium'."
            ) from exc

        port = self._cdp_port()
        stop_browser = threading.Event()
        browser_ready = threading.Event()
        browser_error: list[Exception] = []
        browser_thread = threading.Thread(
            target=self._browser_worker,
            args=(
                sync_playwright,
                port,
                base_url,
                stop_browser,
                browser_ready,
                browser_error,
                self._cancel_event,
                record_video,
                video_recorder,
                frame_stream,
                event_loop,
            ),
            daemon=True,
        )
        browser_thread.start()
        if not browser_ready.wait(timeout=30):
            stop_browser.set()
            browser_thread.join(timeout=5)
            detail = f": {browser_error[0]}" if browser_error else ""
            raise RuntimeError(f"Playwright browser did not become ready{detail}")
        if browser_error:
            raise RuntimeError(f"Playwright browser failed to start: {browser_error[0]}")

        log_dir = Path("logs") / f"AutoGenPlaywrightConfiguration_{task_id or int(time.time())}"
        log_dir.mkdir(parents=True, exist_ok=True)
        transcript: list[dict[str, Any]] = []
        try:
            config = self._llm_config()
            execution_config = {
                "last_n_messages": 3,
                "work_dir": str(log_dir / "web"),
                "use_docker": False,
            }
            coder = autogen.ConversableAgent(
                name="Coder",
                system_message=self._coder_prompt(port),
                llm_config=config,
                human_input_mode="NEVER",
            )
            executor = autogen.UserProxyAgent(
                name="Executor",
                system_message="Execute the Coder's Playwright script and report its result.",
                human_input_mode="NEVER",
                code_execution_config=execution_config,
                llm_config=False,
            )
            analyst = autogen.ConversableAgent(
                name="Analyst",
                system_message=self._analyst_prompt(),
                llm_config=config,
                human_input_mode="NEVER",
            )
            coordinator = autogen.ConversableAgent(
                name="Coordinator",
                system_message=self._coordinator_prompt(task, base_url),
                llm_config=config,
                human_input_mode="NEVER",
            )

            groupchat = autogen.GroupChat(
                agents=[coordinator, coder, executor, analyst],
                messages=[],
                max_round=self.max_iterations,
                speaker_selection_method=self._speaker_selector(
                    coordinator, coder, executor, analyst, self._cancel_event
                ),
            )
            state["groupchat"] = groupchat
            manager = autogen.GroupChatManager(groupchat=groupchat, llm_config=config)
            chat_result = coordinator.initiate_chat(
                manager,
                message=self._start_message(task, base_url),
                summary_method="last_msg",
            )
            transcript = list(chat_result.chat_history)
            statistics = self._statistics(
                transcript,
                {
                    "coordinator": coordinator,
                    "coder": coder,
                    "executor": executor,
                    "analyst": analyst,
                },
            )
            final_text = self._last_text(transcript)
            transcript_text = "\n".join(
                self._message_text(message.get("content")) for message in transcript
            )
            passed = "MAIN GOAL ACHIEVED" in transcript_text
            if browser_error:
                raise RuntimeError(f"Playwright browser failed during execution: {browser_error[0]}")
            return {
                "transcript": transcript,
                "message": final_text or "AutoGen completed without a final status.",
                "passed": passed,
                "statistics": statistics,
                "max_iterations": (
                    not passed
                    and getattr(groupchat, "round", 0) >= self.max_iterations
                ),
            }
        finally:
            stop_browser.set()
            browser_thread.join(timeout=10)

    @staticmethod
    def _statistics(
        transcript: list[dict[str, Any]],
        agents: dict[str, Any],
    ) -> dict[str, Any]:
        by_agent: dict[str, dict[str, int]] = {}
        for message in transcript:
            agent = str(message.get("name", "")).strip().lower()
            if agent not in agents:
                continue
            current = by_agent.setdefault(
                agent,
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0},
            )
            current["calls"] += 1

        for agent_name, agent in agents.items():
            get_usage = getattr(agent, "get_total_usage", None)
            if not callable(get_usage):
                logger.warning("AutoGen agent %s does not expose token usage", agent_name)
                continue
            try:
                usage = get_usage()
            except Exception:
                logger.warning("Could not retrieve AutoGen token usage for %s", agent_name, exc_info=True)
                continue
            if not isinstance(usage, dict):
                logger.warning("AutoGen agent %s returned unsupported token usage data", agent_name)
                continue

            usage = (
                usage.get("usage_excluding_cached_inference")
                or usage.get("usage_including_cached_inference")
                or usage
            )
            if not isinstance(usage, dict):
                logger.warning("AutoGen agent %s returned unsupported token usage data", agent_name)
                continue

            if any(key in usage for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
                model_usages = [usage]
            else:
                model_usages = [
                    model_usage
                    for model_usage in usage.values()
                    if isinstance(model_usage, dict)
                    and any(
                        key in model_usage
                        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    )
                ]
            if not model_usages:
                logger.warning(
                    "AutoGen agent %s returned token usage without recognized model totals",
                    agent_name,
                )
                continue

            current = by_agent.setdefault(
                agent_name,
                {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0},
            )
            for model_usage in model_usages:
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    value = model_usage.get(key, 0)
                    if isinstance(value, (int, float)):
                        current[key] += int(value)
                if not model_usage.get("total_tokens"):
                    current["total_tokens"] += (
                        int(model_usage.get("prompt_tokens", 0) or 0)
                        + int(model_usage.get("completion_tokens", 0) or 0)
                    )

        total = {
            key: sum(agent.get(key, 0) for agent in by_agent.values())
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        return {
            "iterations": (len(transcript) + 3) // 4,
            "llm_calls": sum(agent["calls"] for agent in by_agent.values()),
            "tokens_by_agent": by_agent,
            "tokens_total": total,
        }

    def _browser_worker(
        self,
        sync_playwright: Any,
        port: int,
        base_url: str | None,
        stop_browser: threading.Event,
        browser_ready: threading.Event,
        browser_error: list[Exception],
        cancel_event: threading.Event,
        record_video: bool,
        video_recorder: Any | None,
        frame_stream: BrowserFrameStream | None,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        try:
            with sync_playwright() as playwright:
                headless = self._env_enabled("DEMO_BROWSER_HEADLESS")
                width = int(os.getenv("DEMO_BROWSER_WIDTH", "1920"))
                height = int(os.getenv("DEMO_BROWSER_HEIGHT", "1080"))
                left = int(os.getenv("DEMO_BROWSER_LEFT", "0"))
                top = int(os.getenv("DEMO_BROWSER_TOP", "0"))
                browser = playwright.chromium.launch(
                    headless=headless,
                    args=[
                        f"--remote-debugging-port={port}",
                        f"--window-position={left},{top}",
                    ],
                )
                context = browser.new_context(viewport={"width": width, "height": height})
                try:
                    page = context.new_page()
                    if base_url:
                        page.goto(base_url, wait_until="domcontentloaded")
                    browser_ready.set()
                    consecutive_capture_failures = 0
                    while not stop_browser.is_set():
                        if cancel_event.is_set():
                            break
                        if record_video or frame_stream is not None:
                            captured = self._capture_frame_safely(
                                page,
                                record_video,
                                video_recorder,
                                frame_stream,
                                event_loop,
                                consecutive_capture_failures,
                            )
                            if captured:
                                if consecutive_capture_failures:
                                    logger.info(
                                        "AutoGen browser frame capture recovered after %d failure(s)",
                                        consecutive_capture_failures,
                                    )
                                consecutive_capture_failures = 0
                            else:
                                consecutive_capture_failures += 1
                        stop_browser.wait(0.2 if record_video else 0.5)
                finally:
                    context.close()
                    browser.close()
        except Exception as exc:
            browser_error.append(exc)
            browser_ready.set()

    @staticmethod
    def _capture_frame(
        page: Any,
        record_video: bool,
        video_recorder: Any | None,
        frame_stream: BrowserFrameStream | None,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        frame = page.screenshot(
            type="jpeg",
            quality=65,
            timeout=5000,
            animations="disabled",
        )
        if record_video and video_recorder is not None:
            encoded_frame = base64.b64encode(frame).decode("ascii")
            video_recorder.add_frame(encoded_frame)
        if frame_stream is not None:
            future = asyncio.run_coroutine_threadsafe(frame_stream.publish(frame), event_loop)
            future.result(timeout=8)

    @classmethod
    def _capture_frame_safely(
        cls,
        page: Any,
        record_video: bool,
        video_recorder: Any | None,
        frame_stream: BrowserFrameStream | None,
        event_loop: asyncio.AbstractEventLoop,
        consecutive_failures: int,
    ) -> bool:
        try:
            cls._capture_frame(page, record_video, video_recorder, frame_stream, event_loop)
        except Exception:
            if consecutive_failures == 0 or consecutive_failures % 20 == 19:
                logger.warning(
                    "AutoGen browser frame capture failed; browser execution will continue",
                    exc_info=True,
                )
            return False
        return True

    @staticmethod
    def _env_enabled(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    def _llm_config(self) -> dict[str, Any]:
        provider = self.llm.__class__.__name__
        config: dict[str, Any] = {
            "config_list": [{
                "model": self.llm.model,
                "api_key": self.llm.api_key,
                "base_url": self.llm.base_url,
            }],
            "temperature": 0.2,
            "timeout": 180,
            "cache_seed": None,
        }
        if provider == "AzureModelConfiguration":
            config["config_list"][0].update({
                "api_type": "azure",
                "api_version": self.llm.api_version,
            })
        return config

    @staticmethod
    def _cdp_port() -> int:
        return int(os.getenv("AUTOGEN_PLAYWRIGHT_CDP_PORT", "9222"))

    @staticmethod
    def _last_text(transcript: list[dict[str, Any]]) -> str:
        for message in reversed(transcript):
            content = AutoGenPlaywrightConfiguration._message_text(message.get("content"))
            if content:
                return content
        return ""

    @staticmethod
    def _message_text(content: Any) -> str:
        """Normalize AutoGen text or multimodal content for the SSE payload."""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "\n".join(part.strip() for part in parts if part.strip())
        if content is None:
            return ""
        return str(content)

    @staticmethod
    def _speaker_selector(
        coordinator: Any,
        coder: Any,
        executor: Any,
        analyst: Any,
        cancel_event: threading.Event,
    ):
        def selector(last_speaker: Any, groupchat: Any) -> Any:
            if cancel_event.is_set():
                return None
            messages = groupchat.messages
            latest = str(messages[-1].get("content", "")) if messages else ""
            if "MAIN GOAL ACHIEVED" in latest or "MAIN GOAL NOT ACHIEVED" in latest:
                return None
            if last_speaker is coordinator:
                return coder
            if last_speaker is coder:
                return executor
            if last_speaker is executor:
                return analyst
            return coordinator
        return selector

    @staticmethod
    def _start_message(task: str, base_url: str | None) -> str:
        return f"Execute this web test one action at a time.\nURL: {base_url or 'use the current browser URL'}\n\n{task}"

    @staticmethod
    def _coder_prompt(port: int) -> str:
        return f"""You are the Coder. Write exactly one complete Python Playwright script for the Executor.
Connect to the existing Chromium browser with:
from playwright.sync_api import sync_playwright
with sync_playwright() as playwright:
    browser = playwright.chromium.connect_over_cdp("http://localhost:{port}/")
    page = browser.contexts[0].pages[0]
Only perform the single action requested by the Coordinator, then print the page URL and HTML.
Do not use page.goto(), hidden elements, or multiple actions across navigation."""

    @staticmethod
    def _analyst_prompt() -> str:
        return """You are the Analyst. Inspect the Executor result and HTML. Report precise visible
interaction elements and whether the previous action succeeded. Do not perform browser actions."""

    @staticmethod
    def _coordinator_prompt(task: str, base_url: str | None) -> str:
        return f"""You are the Coordinator. Achieve this complete test:
{task}
The starting URL is {base_url or 'the current browser URL'}.
Assign one precise browser action at a time. When every requirement is satisfied,
write MAIN GOAL ACHIEVED. If it cannot be completed, write MAIN GOAL NOT ACHIEVED."""
