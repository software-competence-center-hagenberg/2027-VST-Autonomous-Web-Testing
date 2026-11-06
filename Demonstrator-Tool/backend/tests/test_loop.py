import asyncio

from agents.loop import run_agents_loop


class StubAgent:
    def __init__(self, agent_name: str, decisions: list[str]):
        self.agent_name = agent_name
        self.decisions = iter(decisions)

    async def decide(self, context):
        return {"type": next(self.decisions), "payload": None}


def test_only_authorized_agent_can_stop_loop():
    async def run():
        agents = [
            StubAgent("analyst", ["continue", "continue"]),
            StubAgent("coordinator", ["continue", "stop"]),
            StubAgent("browser", ["stop"]),
            StubAgent("observer", ["continue"]),
        ]
        context = {"storage": {}, "messages": []}
        return [
            event async for event in run_agents_loop(
                agents,
                context,
                max_iterations=3,
                stop_agent_name="coordinator",
            )
        ]

    events = asyncio.run(run())

    assert [event.data["step"] for event in events if event.type == "step_start"] == [1, 2]
    browser_decision = next(
        event for event in events
        if event.type == "agent_decision" and event.data["agent"] == "browser"
    )
    assert browser_decision.data["decision_type"] == "stop"
    assert browser_decision.data["stop_ignored"] is True
    assert events[-1].type == "stopped"


def test_any_agent_can_stop_when_no_authority_is_configured():
    async def run():
        context = {"storage": {}, "messages": []}
        return [
            event async for event in run_agents_loop(
                [StubAgent("browser", ["stop"])],
                context,
                max_iterations=1,
            )
        ]

    events = asyncio.run(run())

    assert events[-1].type == "stopped"
