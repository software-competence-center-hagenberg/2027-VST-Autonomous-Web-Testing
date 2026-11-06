"""Pydantic schemas used by the FastAPI backend."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["pending", "running", "completed", "failed", "stopped"]
ModelProvider = Literal["vllm", "azure", "openai"]


class ConfigurationInfo(BaseModel):
    """Describes one selectable agent configuration."""

    id: str
    display_name: str
    description: str
    agents: list[str]


class CreateTaskRequest(BaseModel):
    """Body for POST /api/tasks - start a new agent run."""

    configuration: str = Field(..., description="One of the ids returned by GET /api/configurations")
    provider: ModelProvider = Field(..., description="Configured model provider: vllm, azure, or openai")
    model: str = Field(..., min_length=1, description="Model id (or Azure deployment name)")
    task: str = Field(..., description="The task/test case (e.g. a Gherkin scenario) to hand to the agents")
    base_url: str | None = Field(None, description="URL the browser should navigate to before the run starts")
    num_task_executions: int = Field(1, ge=1, le=20, description="How many times to run the task end-to-end")
    max_iterations: int = Field(50, ge=1, le=500, description="Max agent-loop iterations per execution")
    vision_enabled: bool = Field(True, description="Whether the browser agent should use screenshots (multimodal)")
    record_video: bool = Field(False, description="Whether to save an MP4 recording of the browser run")


class AgentEvent(BaseModel):
    """One step in the recorded conversation between agents."""

    type: str
    data: dict[str, Any]
    timestamp: float
    execution_index: int


class TaskSummary(BaseModel):
    """Lightweight view of a task run, for list views."""

    id: str
    configuration: str
    provider: ModelProvider
    model: str
    task: str
    base_url: str | None
    status: TaskStatus
    current_execution: int
    num_task_executions: int
    max_iterations: int
    vision_enabled: bool
    record_video: bool = False
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    archived: bool = False
    video_available: bool = False


class TaskDetail(TaskSummary):
    """Full view of a task run, including the recorded agent conversation."""

    events: list[AgentEvent]
    statistics: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
