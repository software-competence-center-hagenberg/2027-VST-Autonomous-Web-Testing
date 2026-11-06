# agents/loop.py
import logging
from typing import AsyncIterator, Sequence

from openai.types.chat import ChatCompletionSystemMessageParam

from agents.agents import AgentContext, AgentDecision, BaseAgent
from events import Event

logger = logging.getLogger(__name__)


async def run_agents_loop(
    agents: Sequence[BaseAgent],
    context: AgentContext,
    max_iterations: int = 20,
    stop_agent_name: str | None = None,
) -> AsyncIterator[Event]:
    """
    Run a list of agents in a loop, updating the shared context, yielding an
    Event at every step boundary and agent decision.

    This is the single source of truth for the agent loop; callers (CLI,
    FastAPI backend, ...) consume the events to drive their own side effects
    (printing, screenshots, persistence, SSE) instead of the loop knowing
    about any of them.

    - agents: list of BaseAgent agents
    - context: shared AgentContext, mutated in place as agents run
    - max_iterations: maximum iterations for the loop
    - stop_agent_name: optional agent authorized to stop the loop
    """
    step = 0
    while True:
        step += 1
        context["storage"]["iterations"] = step
        yield Event(type="step_start", data={"step": step})

        stopped = False
        for agent in agents:
            decision: AgentDecision = await agent.decide(context)
            decisions = context["storage"].setdefault("agent_decisions", {})
            decisions[agent.agent_name] = decisions.get(agent.agent_name, 0) + 1

            stop_ignored = (
                decision["type"] == "stop"
                and stop_agent_name is not None
                and agent.agent_name != stop_agent_name
            )
            decision_data = {
                "step": step,
                "agent": agent.agent_name,
                "call_id": f"{step}:{agent.agent_name}",
                "decision_type": decision["type"],
                "payload": decision["payload"],
            }
            if stop_ignored:
                decision_data["stop_ignored"] = True
            yield Event(type="agent_decision", data=decision_data)

            if stop_ignored:
                logger.warning(
                    "Ignoring stop decision from agent '%s'; only '%s' may stop this configuration",
                    agent.agent_name,
                    stop_agent_name,
                )
            elif decision["type"] == "stop":
                stopped = True
                break

        # Let callers react (screenshot, persist, ...) once per step, stop or not.
        yield Event(type="step_complete", data={"step": step})

        if stopped:
            event_type = "completed" if context["storage"].get("test_passed", False) else "stopped"
            stop_data = {"step": step}
            if isinstance(decision.get("payload"), dict):
                stop_data.update(decision["payload"])
            yield Event(type=event_type, data=stop_data)
            return

        if step >= max_iterations:
            context["messages"].append(ChatCompletionSystemMessageParam(
                role="system",
                content="[LOOP ABORTED] Max iterations reached.",
            ))
            yield Event(type="max_iterations", data={"step": step})
            return
