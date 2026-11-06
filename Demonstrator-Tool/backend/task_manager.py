"""
Runs agent configurations in the background and keeps track of the resulting
conversation (the stream of `Event`s each run produces) so it can be polled
or streamed by the API.

Task state is kept in memory while the process runs and mirrored to one JSON
record per task under `tasks/` so completed history survives restarts.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any
from pathlib import Path

from agents.factory import CONFIGURATIONS, build_configuration, build_model_configuration, list_configurations
from schemas import CreateTaskRequest
from browser_stream import close_browser_stream
from browser_use.browser.video_recorder import VideoRecorderService

logger = logging.getLogger(__name__)

# Sentinel put on a subscriber queue to signal "no more events will arrive".
STREAM_DONE = object()


@dataclass
class TaskRun:
    id: str
    configuration: str
    provider: str
    model: str
    task: str
    base_url: str | None
    num_task_executions: int
    max_iterations: int
    vision_enabled: bool
    record_video: bool = False
    video_available: bool = False
    archived: bool = False
    undeletable: bool = False

    status: str = "pending"
    current_execution: int = 0
    error: str | None = None
    statistics: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    events: list[dict[str, Any]] = field(default_factory=list)

    _subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False, compare=False)
    _asyncio_task: asyncio.Task | None = field(default=None, repr=False, compare=False)
    _active_configuration: Any = field(default=None, repr=False, compare=False)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def subscribe(self) -> asyncio.Queue:
        """Register a queue that receives every future event (used for streaming)."""
        queue: asyncio.Queue = asyncio.Queue()
        # Replay history so a client that connects mid-run doesn't miss steps.
        for event in self.events:
            queue.put_nowait(event)
        if self.status in ("completed", "failed", "stopped"):
            queue.put_nowait(STREAM_DONE)
        self._subscribers.append(queue)
        return queue

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "configuration": self.configuration,
            "provider": self.provider,
            "model": self.model,
            "task": self.task,
            "base_url": self.base_url,
            "num_task_executions": self.num_task_executions,
            "max_iterations": self.max_iterations,
            "vision_enabled": self.vision_enabled,
            "record_video": self.record_video,
            "video_available": self.video_available,
            "archived": self.archived,
            "undeletable": self.undeletable,
            "status": self.status,
            "current_execution": self.current_execution,
            "error": self.error,
            "statistics": self.statistics,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "events": self.events,
        }

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def publish(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        self.touch()
        # Persistence is handled by TaskManager after publication.
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    def finish(self) -> None:
        for queue in list(self._subscribers):
            queue.put_nowait(STREAM_DONE)


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRun] = {}
        self._persist_locks: dict[str, threading.Lock] = {}
        self._task_change_subscribers: list[asyncio.Queue[None]] = []
        self._storage_dir = Path(__file__).resolve().parent / "tasks"
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._load_tasks()

    def subscribe_task_changes(self) -> asyncio.Queue[None]:
        queue: asyncio.Queue[None] = asyncio.Queue(maxsize=1)
        self._task_change_subscribers.append(queue)
        return queue

    def unsubscribe_task_changes(self, queue: asyncio.Queue[None]) -> None:
        if queue in self._task_change_subscribers:
            self._task_change_subscribers.remove(queue)

    def notify_task_changes(self) -> None:
        for queue in list(self._task_change_subscribers):
            if queue.empty():
                queue.put_nowait(None)

    @staticmethod
    def retention_seconds() -> int:
        try:
            return max(0, int(os.getenv("DEMO_TASK_RETENTION_SECONDS", "0")))
        except ValueError:
            logger.warning("Ignoring invalid DEMO_TASK_RETENTION_SECONDS")
            return 0

    async def cleanup_expired_tasks(self) -> int:
        retention = self.retention_seconds()
        if retention <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=retention)
        expired = [
            run for run in self._tasks.values()
            if not run.archived
            and not run.undeletable
            and run.status in ("completed", "failed", "stopped")
            and run.updated_at < cutoff
        ]
        for run in expired:
            self._delete_task(run)
        return len(expired)

    def _delete_task(self, run: TaskRun) -> bool:
        if run.archived or run.undeletable:
            return False
        (self._storage_dir / f"{run.id}.json").unlink(missing_ok=True)
        task_directory = self._storage_dir / run.id
        if task_directory.exists():
            shutil.rmtree(task_directory)
        self._tasks.pop(run.id, None)
        self._persist_locks.pop(run.id, None)
        self.notify_task_changes()
        return True

    def video_path(self, task_id: str) -> Path:
        return self._storage_dir / task_id / "video" / "recording.mp4"

    def _persist(self, run: TaskRun) -> None:
        path = self._storage_dir / f"{run.id}.json"
        # Use a unique sibling file: browser-use events can arrive while
        # another task update is being persisted, and sharing one `.tmp` path
        # causes Windows to reject the second replace with WinError 5.
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        lock = self._persist_locks.setdefault(run.id, threading.Lock())
        with lock:
            try:
                temporary.write_text(
                    json.dumps(run.to_record(), ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8",
                )
                for attempt in range(8):
                    try:
                        os.replace(temporary, path)
                        break
                    except PermissionError:
                        if attempt == 7:
                            raise
                        time.sleep(0.05 * (attempt + 1))
            finally:
                temporary.unlink(missing_ok=True)

    async def _persist_async(self, run: TaskRun) -> None:
        await asyncio.to_thread(self._persist, run)

    def _load_tasks(self) -> None:
        for path in sorted(self._storage_dir.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                status = record.get("status", "failed")
                if status in ("pending", "running"):
                    status = "stopped"
                    record["error"] = "Backend restarted while this task was running"
                events = record.get("events", [])
                cleaned_events = [
                    event for event in events
                    if event.get("type") != "run_statistics"
                ]
                statistics = record.get("statistics", {})
                if not statistics:
                    legacy_statistics = next(
                        (
                            event.get("data", {})
                            for event in events
                            if event.get("type") == "run_statistics"
                        ),
                        {},
                    )
                    statistics = legacy_statistics
                run = TaskRun(
                    id=record["id"],
                    configuration=record["configuration"],
                    provider=record["provider"],
                    model=record["model"],
                    task=record["task"],
                    base_url=record.get("base_url"),
                    num_task_executions=record.get("num_task_executions", 1),
                    max_iterations=record.get("max_iterations", 50),
                    vision_enabled=record.get("vision_enabled", True),
                    record_video=record.get("record_video", False),
                    video_available=record.get("video_available", False),
                    archived=record.get("archived", False),
                    undeletable=record.get("undeletable", False),
                    status=status,
                    current_execution=record.get("current_execution", 0),
                    error=record.get("error"),
                    statistics=statistics,
                    result=record.get("result"),
                    created_at=datetime.fromisoformat(record["created_at"]),
                    updated_at=datetime.fromisoformat(record["updated_at"]),
                    events=cleaned_events,
                )
                self._tasks[run.id] = run
                if (
                    record.get("status") in ("pending", "running")
                    or len(cleaned_events) != len(events)
                ):
                    self._persist(run)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Skipping invalid persisted task %s: %s", path, exc)

    # ---------------- configurations ----------------

    def list_configurations(self) -> list[dict]:
        return list_configurations()

    # ---------------- tasks ----------------

    def create_task(self, request: CreateTaskRequest) -> TaskRun:
        if request.configuration not in CONFIGURATIONS:
            raise ValueError(
                f"Unknown agent configuration: {request.configuration!r}. "
                f"Available: {sorted(CONFIGURATIONS)}"
            )
        if not request.model.strip():
            raise ValueError("Model must not be blank")
        # Validate provider configuration before creating a run, while keeping
        # all credentials and endpoint details on the server.
        build_model_configuration(provider=request.provider, model=request.model.strip())

        run = TaskRun(
            id=str(uuid.uuid4()),
            configuration=request.configuration,
            provider=request.provider,
            model=request.model.strip(),
            task=request.task,
            base_url=request.base_url,
            num_task_executions=request.num_task_executions,
            max_iterations=request.max_iterations,
            vision_enabled=request.vision_enabled,
            record_video=request.record_video,
        )
        self._tasks[run.id] = run
        self._persist(run)
        self.notify_task_changes()
        run._asyncio_task = asyncio.create_task(self._execute(run))
        return run

    def get_task(self, task_id: str) -> TaskRun | None:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskRun]:
        return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    def set_archived(self, task_id: str, archived: bool) -> TaskRun | None:
        run = self._tasks.get(task_id)
        if run is None:
            return None
        run.archived = archived
        run.touch()
        self._persist(run)
        self.notify_task_changes()
        return run

    async def clear_tasks(self) -> int:
        """Stop active runs and remove every persisted task record and asset."""
        runs = list(self._tasks.values())
        for run in runs:
            if run.archived or run.undeletable:
                continue
            if run._asyncio_task is not None and not run._asyncio_task.done():
                await self.cancel_task(run.id)

        removed = 0
        for run in runs:
            if self._delete_task(run):
                removed += 1
        return removed

    async def cancel_task(self, task_id: str) -> bool:
        run = self._tasks.get(task_id)
        if run is None or run._asyncio_task is None or run._asyncio_task.done():
            return False

        cancel = getattr(run._active_configuration, "cancel", None)
        if cancel is not None:
            cancel()
        run._asyncio_task.cancel()
        try:
            await run._asyncio_task
        except asyncio.CancelledError:
            pass

        run.status = "stopped"
        run.error = "Task cancelled by the user"
        run.touch()
        self._persist(run)
        self.notify_task_changes()
        run.finish()
        return True

    # ---------------- execution ----------------

    async def _execute(self, run: TaskRun) -> None:
        run.status = "running"
        run.touch()
        await self._persist_async(run)
        self.notify_task_changes()
        execution_failed = False
        video_recorder = None
        try:
            if run.record_video:
                width = int(os.getenv("DEMO_BROWSER_WIDTH", "1920"))
                height = int(os.getenv("DEMO_BROWSER_HEIGHT", "1080"))
                video_recorder = VideoRecorderService(
                    output_path=self.video_path(run.id),
                    size={"width": width, "height": height},
                    framerate=5,
                )
                await asyncio.to_thread(video_recorder.start)

            for execution_index in range(1, run.num_task_executions + 1):
                run.current_execution = execution_index
                run.touch()
                await self._persist_async(run)
                self.notify_task_changes()

                configuration = build_configuration(
                    run.configuration,
                    provider=run.provider,
                    model=run.model,
                    num_task_executions=run.num_task_executions,
                    max_iterations=run.max_iterations,
                    vision_enabled=run.vision_enabled,
                )
                run._active_configuration = configuration

                async for event in configuration.run(
                    task=run.task,
                    base_url=run.base_url,
                    task_id=f"{run.id}_{execution_index}",
                    record_video=run.record_video,
                    video_recorder=video_recorder,
                ):
                    if event.type in ("completed", "stopped", "max_iterations"):
                        run.statistics = configuration.last_statistics
                    if event.type in ("completed", "stopped", "max_iterations", "error"):
                        run.result = event.data
                    payload = event.to_dict()
                    payload["execution_index"] = execution_index
                    run.publish(payload)
                    await self._persist_async(run)

                    if event.type in ("error", "stopped", "max_iterations"):
                        execution_failed = True
                        if event.type == "error":
                            run.error = event.data.get("message") or "Agent configuration failed"
                        elif event.type == "stopped":
                            message = event.data.get("message")
                            run.error = (
                                f"Task stopped before completion: {message}"
                                if message
                                else "Task stopped before completion"
                            )
                        else:
                            step = event.data.get("step")
                            run.error = (
                                f"Maximum iteration limit reached at step {step}"
                                if step is not None
                                else "Maximum iteration limit reached"
                            )

            run.status = "failed" if execution_failed else "completed"
            await self._persist_async(run)
        except asyncio.CancelledError:
            run.status = "stopped"
            run.error = "Task cancelled by the user"
            await self._persist_async(run)
            raise
        except Exception as exc:  # noqa: BLE001 - surface any failure to the API
            logger.exception("Task %s failed", run.id)
            run.status = "failed"
            run.error = str(exc)
            await self._persist_async(run)
        finally:
            if video_recorder is not None:
                await asyncio.to_thread(video_recorder.stop_and_save)
                video_path = self.video_path(run.id)
                run.video_available = video_path.is_file() and video_path.stat().st_size > 0
            run._active_configuration = None
            run.touch()
            await self._persist_async(run)
            self.notify_task_changes()
            await close_browser_stream(run.id)
            run.finish()


# Single, process-wide instance used by the FastAPI app.
task_manager = TaskManager()
