import asyncio

from agents.autogen_playwright_configuration import AutoGenPlaywrightConfiguration
from browser_stream import BrowserFrameStream


class StubAgent:
    def __init__(self, usage):
        self.usage = usage

    def get_total_usage(self):
        return self.usage


def test_autogen_statistics_match_shared_run_statistics_shape():
    transcript = [
        {"name": "Coordinator", "content": "Click the button"},
        {"name": "Coder", "content": "Write script"},
        {"name": "Executor", "content": "Clicked"},
        {"name": "Analyst", "content": "Action succeeded"},
    ]
    agents = {
        "coordinator": StubAgent({
            "total_cost": 0.001,
            "test-model": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "cost": 0.001,
            },
            "another-test-model": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
                "cost": 0.0001,
            },
        }),
        "coder": StubAgent({
            "prompt_tokens": 80,
            "completion_tokens": 15,
            "total_tokens": 95,
        }),
        "executor": StubAgent({}),
        "analyst": StubAgent({
            "prompt_tokens": 50,
            "completion_tokens": 10,
            "total_tokens": 60,
        }),
    }

    statistics = AutoGenPlaywrightConfiguration._statistics(transcript, agents)

    assert statistics == {
        "iterations": 1,
        "llm_calls": 4,
        "tokens_by_agent": {
            "coordinator": {
                "prompt_tokens": 110,
                "completion_tokens": 22,
                "total_tokens": 132,
                "calls": 1,
            },
            "coder": {
                "prompt_tokens": 80,
                "completion_tokens": 15,
                "total_tokens": 95,
                "calls": 1,
            },
            "executor": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "calls": 1,
            },
            "analyst": {
                "prompt_tokens": 50,
                "completion_tokens": 10,
                "total_tokens": 60,
                "calls": 1,
            },
        },
        "tokens_total": {
            "prompt_tokens": 240,
            "completion_tokens": 47,
            "total_tokens": 287,
        },
    }


def test_autogen_statistics_accept_empty_transcript():
    assert AutoGenPlaywrightConfiguration._statistics([], {}) == {
        "iterations": 0,
        "llm_calls": 0,
        "tokens_by_agent": {},
        "tokens_total": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


def test_autogen_browser_settings_read_headless_flag(monkeypatch):
    monkeypatch.setenv("DEMO_BROWSER_HEADLESS", "yes")

    assert AutoGenPlaywrightConfiguration._env_enabled("DEMO_BROWSER_HEADLESS")


def test_autogen_frame_capture_publishes_to_browser_stream():
    class StubPage:
        def screenshot(self, **kwargs):
            assert kwargs == {
                "type": "jpeg",
                "quality": 65,
                "timeout": 5000,
                "animations": "disabled",
            }
            return b"jpeg-frame"

    class StubVideoRecorder:
        def __init__(self):
            self.frames = []

        def add_frame(self, frame):
            self.frames.append(frame)

    recorder = StubVideoRecorder()

    async def capture_and_wait():
        frame_stream = BrowserFrameStream()
        event_loop = asyncio.get_running_loop()
        await asyncio.to_thread(
            AutoGenPlaywrightConfiguration._capture_frame,
            StubPage(),
            True,
            recorder,
            frame_stream,
            event_loop,
        )
        return await frame_stream.wait_for_frame(0)

    frame, version, closed = asyncio.run(capture_and_wait())

    assert frame == b"jpeg-frame"
    assert version == 1
    assert not closed
    assert recorder.frames == ["anBlZy1mcmFtZQ=="]


def test_autogen_frame_capture_failure_does_not_stop_browser():
    class ClosedPage:
        def screenshot(self, **kwargs):
            raise RuntimeError("Page.captureScreenshot failed during navigation")

    event_loop = asyncio.new_event_loop()
    try:
        assert not AutoGenPlaywrightConfiguration._capture_frame_safely(
            ClosedPage(),
            record_video=False,
            video_recorder=None,
            frame_stream=None,
            event_loop=event_loop,
            consecutive_failures=0,
        )
    finally:
        event_loop.close()
