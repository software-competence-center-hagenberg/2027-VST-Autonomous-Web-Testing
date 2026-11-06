from typing import Any

from agents.agents import AgentDecision
from agents.tools import Tool

from openai.types.chat import ChatCompletionToolMessageParam

class PerformActionTool(Tool):
    name = "perform_action"
    description = "Perform exactly ONE browser action."
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "A browser action, e.g. "
                    "'CLICK_BUTTON:Submit', "
                    "'CLICK_BUTTON:Add User', "
                    "'CLICK_LINK:Edit User', "
                    "'CLICK_LINK:Index[333]', "
                    "'FILL_FORM:{firstname:John,lastname:Doe}', "
                    "'NAVIGATE:TO:http://localhost:8080/add/person', "
                    "'GO_BACK'"
                ),
            }
        },
        "required": ["action"],
    }

    async def run(self, arguments: dict[str, Any]) -> Any:
        return arguments["action"]


class StopTool(Tool):
    name = "stop"
    description = "Stop execution because the test is complete or cannot proceed."
    parameters = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": (
                    "Optional reason for stopping. For instance: "
                    "The test is complete and finished as expected. "
                    "The test failed, because of ... ."
                    "The test could not be completed, because ... ."
                ),
            },
            "passed": {
                "type": "boolean",
                "description": "Whether the task/test passed.",
            },
        },
    }

    async def run(self, arguments: dict[str, Any]) -> Any:
        return {
            "reason": arguments.get("reason"),
            "passed": arguments.get("passed", False)
        }
    
# special tool handler functions
async def handle_perform_action(args, context, messages, tool_call_id):
    action = args["action"]
    context["storage"].setdefault("action_history", []).append(action)
    context["task"] = action

    context["messages"].append(ChatCompletionToolMessageParam(
        role="tool",
        content=action,
        tool_call_id=tool_call_id
    ))

    return AgentDecision(type="continue", payload=action)


async def handle_stop(args, context, messages, tool_call_id):
    reason = args.get("reason")
    passed = bool(args.get("passed", False))
    context["storage"]["test_passed"] = passed

    status_text = "PASSED" if passed else "STOPPED"
    message = f"Stop execution ({status_text}): {reason}"

    context["messages"].append(ChatCompletionToolMessageParam(
        role="tool",
        content=message,
        tool_call_id=tool_call_id
    ))

    return AgentDecision(type="stop", payload={"message": message, "passed": passed})

class ContinueTool(Tool):
    name = "continue"
    description = "Signal that the test should continue or retry execution."
    parameters = {
        "type": "object",
        "properties": {
            "hint": {
                "type": "string",
                "description": "Optional hint or instruction for the next attempt.",
            }
        },
    }

    async def run(self, arguments: dict[str, Any]) -> Any:
        # Just return the hint if any
        return {"hint": arguments.get("hint", None)}

async def handle_continue(args: dict, context: dict, messages: list) -> "AgentDecision":
    hint = args.get("hint", None)
    
    # Append hint to existing task if provided
    if hint:
        context["task"] += f"\n\nAdditional hint from pevious execution: {hint}"

    # Record the continue action in the chat history
    context["messages"].append({
        "role": "assistant",
        "content": f"Continue execution{f' with hint: {hint}' if hint else ''}",
        "name": "observer",  # or whichever agent called it
    })

    return AgentDecision(type="continue", payload={"hint": hint})
