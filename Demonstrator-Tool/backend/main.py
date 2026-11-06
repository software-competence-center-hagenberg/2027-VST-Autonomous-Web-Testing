"""
FastAPI backend for the multi-agent web-testing system.

Endpoints
---------
GET    /api/configurations        list the agent configurations that can be used
POST   /api/tasks                 give the agents a task (start a run)
GET    /api/tasks                 list all task runs
GET    /api/tasks/stream          Server-Sent Events for task-list changes
GET    /api/tasks/{task_id}       full detail of one run, including the full
                                   recorded conversation between agents
GET    /api/tasks/{task_id}/stream  live-stream the conversation (Server-Sent Events)
DELETE /api/tasks/{task_id}       cancel a running task
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from schemas import ConfigurationInfo, CreateTaskRequest, TaskDetail, TaskSummary
from task_manager import STREAM_DONE, TaskRun, task_manager
from agents.factory import discover_models
from safety_guard import classify_task
from browser_stream import find_browser_stream, get_browser_stream


def safety_guard_enabled() -> bool:
    return os.getenv("DEMO_SAFETY_GUARD", "").strip().lower() in {"1", "true", "yes", "on"}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agent Testing Backend",
    description="Run and observe multi-agent web-testing configurations.",
    version="1.0.0",
)

@app.on_event("startup")
async def start_task_retention_cleanup() -> None:
    retention = task_manager.retention_seconds()
    if retention <= 0:
        return

    async def cleanup_loop() -> None:
        while True:
            await task_manager.cleanup_expired_tasks()
            await asyncio.sleep(min(max(retention, 60), 3600))

    app.state.task_cleanup = asyncio.create_task(cleanup_loop())

# Wide-open CORS for local development; restrict this to your frontend's
# origin(s) before deploying anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _to_summary(run: TaskRun) -> TaskSummary:
    return TaskSummary(
        id=run.id,
        configuration=run.configuration,
        provider=run.provider,
        model=run.model,
        task=run.task,
        base_url=run.base_url,
        status=run.status,
        current_execution=run.current_execution,
        num_task_executions=run.num_task_executions,
        max_iterations=run.max_iterations,
        vision_enabled=run.vision_enabled,
        record_video=run.record_video,
        video_available=run.video_available,
        created_at=run.created_at,
        updated_at=run.updated_at,
        error=run.error,
        archived=run.archived,
    )


def _to_detail(run: TaskRun) -> TaskDetail:
    return TaskDetail(
        **_to_summary(run).model_dump(),
        events=run.events,
        statistics=run.statistics,
        result=run.result,
    )


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/api/configurations", response_model=list[ConfigurationInfo])
async def get_configurations() -> list[ConfigurationInfo]:
    """List every agent configuration that can be selected for a task."""
    return task_manager.list_configurations()


@app.get("/api/models")
async def get_models() -> dict:
    """Discover models from every configured provider without exposing credentials."""
    return await discover_models()


@app.post("/api/tasks", response_model=TaskDetail, status_code=201)
async def create_task(request: CreateTaskRequest) -> TaskDetail:
    """Give the agents a task. Runs in the background; stream to observe it."""
    try:
        if safety_guard_enabled():
            try:
                safety = await classify_task(
                    provider=request.provider,
                    model=request.model.strip(),
                    url=request.base_url,
                    task=request.task,
                )
            except Exception as exc:
                logger.exception("Safety classification failed; refusing task: %s", exc)
                raise HTTPException(
                    status_code=503,
                    detail="Task safety check unavailable; the task was not started.",
                ) from exc
            if safety["decision"] != "ACCEPT":
                raise HTTPException(status_code=400, detail={"message": "Task rejected by safety guard", **safety})
        run = task_manager.create_task(request)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_detail(run)


@app.get("/api/tasks", response_model=list[TaskSummary])
async def list_tasks() -> list[TaskSummary]:
    return [_to_summary(run) for run in task_manager.list_tasks()]


@app.get("/api/tasks/stream")
async def stream_task_changes() -> StreamingResponse:
    """Notify connected clients when a task is created, updated, or deleted."""

    async def event_source():
        queue = task_manager.subscribe_task_changes()
        try:
            while True:
                try:
                    await asyncio.wait_for(queue.get(), timeout=15)
                    yield "data: {\"type\":\"tasks_changed\"}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            task_manager.unsubscribe_task_changes(queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/tasks/{task_id}", response_model=TaskDetail)
async def get_task(task_id: str) -> TaskDetail:
    """Full detail of a run, including every recorded agent decision so far."""
    run = task_manager.get_task(task_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_detail(run)


@app.get("/api/tasks/{task_id}/stream")
async def stream_task(task_id: str) -> StreamingResponse:
    """
    Live-stream the conversation between agents as Server-Sent Events.

    Replays everything recorded so far and then pushes new events as they
    happen, so this works whether you connect before, during, or after a run.
    Each event is a JSON object shaped like schemas.AgentEvent.
    """
    run = task_manager.get_task(task_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_source():
        queue = run.subscribe()
        try:
            while True:
                item = await queue.get()
                if item is STREAM_DONE:
                    yield "event: done\ndata: {}\n\n"
                    break
                yield f"data: {json.dumps(item)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            run.unsubscribe(queue)

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.get("/api/tasks/{task_id}/screenshots/{filename}")
async def get_task_screenshot(task_id: str, filename: str) -> FileResponse:
    """Serve a screenshot belonging to a persisted browser-use run."""
    if Path(filename).name != filename or not filename.endswith(".png"):
        raise HTTPException(status_code=404, detail="Screenshot not found")
    tasks_dir = Path(__file__).resolve().parent / "tasks"
    matches = list(tasks_dir.glob(f"{task_id}*/screenshots/{filename}"))
    if not matches:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(matches[0], media_type="image/png")


@app.get("/api/tasks/{task_id}/video")
async def get_task_video(task_id: str) -> FileResponse:
    """Serve the completed MP4 recording belonging to a task."""
    run = task_manager.get_task(task_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")
    video_path = task_manager.video_path(task_id)
    if not run.video_available or not video_path.is_file():
        raise HTTPException(status_code=404, detail="Video recording not found")
    return FileResponse(video_path, media_type="video/mp4", filename="recording.mp4")


@app.get("/api/tasks/{task_id}/browser-stream")
async def stream_browser(task_id: str) -> StreamingResponse:
    run = task_manager.get_task(task_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")
    stream = find_browser_stream(task_id)
    if stream is None:
        if run.status != "running":
            raise HTTPException(status_code=404, detail="No browser preview is available")
        stream = get_browser_stream(task_id)

    async def frames():
        version = 0
        while True:
            frame, version, closed = await stream.wait_for_frame(version)
            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode("ascii") + b"\r\n\r\n"
                    + frame + b"\r\n"
                )
            if closed:
                break

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/tasks")
async def clear_tasks() -> dict:
    """Stop active tasks and clear all task history and screenshots."""
    return {"deleted": await task_manager.clear_tasks()}


@app.patch("/api/tasks/{task_id}/archive", response_model=TaskDetail)
async def archive_task(task_id: str, archived: bool = True) -> TaskDetail:
    run = task_manager.set_archived(task_id, archived)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_detail(run)


@app.delete("/api/tasks/{task_id}")
async def cancel_task(task_id: str) -> dict:
    run = task_manager.get_task(task_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Task not found")

    cancelled = await task_manager.cancel_task(task_id)
    if not cancelled:
        return {"cancelled": False, "reason": "Task already finished"}
    return {"cancelled": True}


# Serve the pre-built frontend (container mode). Mounted last so every /api
# route above takes precedence. Skipped when no build exists (local dev uses
# the Vite dev server instead).
_FRONTEND_DIST = Path(
    os.getenv("FRONTEND_DIST") or Path(__file__).resolve().parent.parent / "frontend" / "dist"
)
if (_FRONTEND_DIST / "index.html").is_file():
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
