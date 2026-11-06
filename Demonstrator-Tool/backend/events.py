"""
Event objects yielded by `agents.loop.run_agents_loop` (and, in turn, by
`AgentConfiguration.run`) to report progress of a multi-agent run.

This module was referenced by `agents/loop.py` and `agents/agent_configurations.py`
(`from events import Event`) but was missing from the original project - it is
recreated here so the package is importable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

EventType = Literal[
    "step_start",
    "agent_decision",
    "step_complete",
    "stopped",
    "completed",
    "max_iterations",
    "error",
    "browser_internal_step",
]


@dataclass
class Event:
    """A single, JSON-serializable progress event."""

    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
        }
