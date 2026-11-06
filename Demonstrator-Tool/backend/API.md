# Agent Testing API

This document describes the HTTP API exposed by the backend. The API is
intended for a frontend that lets users select a model, start a browser test,
and observe the run live.

## Base URL

When running locally:

```text
http://localhost:8000
```

Interactive OpenAPI documentation is also available at `/docs`.

The API currently has no authentication requirement and allows cross-origin
requests for local development.

## Common conventions

- Request and response bodies use JSON.
- Timestamps are ISO 8601 UTC strings in task responses.
- A task runs in the background. Creating a task does not wait for the browser
  test to finish.
- Task data is mirrored to `tasks/<task-id>.json` and loaded when the
  backend starts.

## `GET /api/health`

Checks whether the backend is responding.

### Response `200`

```json
{
  "status": "ok"
}
```

## `GET /api/configurations`

Returns the agent configurations that can be selected when creating a task.

### Response `200`

```json
[
  {
    "id": "BrowserOnlyConfiguration",
    "display_name": "Browser Only",
    "description": "A single browser-use agent receives the whole Gherkin test case as its task and executes it autonomously end-to-end, without any other agents overseeing it.",
    "agents": ["browser"]
  },
  {
    "id": "FourAgentConfiguration",
    "display_name": "Four Agent (shared history)",
    "description": "Four agents collaborate over a shared conversation history: an analyst decides the next high-level intent, a coordinator turns that intent into a single atomic browser action, a browser agent executes it, and an observer checks whether execution is still on track.",
    "agents": ["analyst", "coordinator", "browser", "observer"]
  },
  {
    "id": "FourAgentConfiguration_STATE",
    "display_name": "Four Agent (state-based)",
    "description": "Four agents use state-based interactions: the analyst proposes the next intent, the coordinator executes one browser action, the browser agent performs it, and the observer evaluates the latest result against the original test goal.",
    "agents": ["analyst", "coordinator", "browser", "observer"]
  },
  {
    "id": "AutoGenPlaywrightConfiguration",
    "display_name": "AutoGen Playwright",
    "description": "Experimental AutoGen coordinator, coder, executor, and analyst workflow using generated Playwright scripts.",
    "agents": ["coordinator", "coder", "executor", "analyst"]
  }
]
```

Use the returned `id` as the `configuration` value in `POST /api/tasks`.

## `GET /api/models`

Discovers models from all configured vendors concurrently. Credentials and
endpoint URLs are never returned.

### Response `200`

```json
{
  "vllm": {
    "models": ["RedHatAI/gemma-4-31B-it-FP8-Dynamic"],
    "configured": true,
    "reachable": true,
    "error": null
  },
  "azure": {
    "models": [],
    "configured": false,
    "reachable": false,
    "error": null
  },
  "openai": {
    "models": [],
    "configured": false,
    "reachable": false,
    "error": null
  }
}
```

Each provider has:

- `models`: model IDs returned by the provider.
- `configured`: whether the required server-side environment variables exist.
- `reachable`: whether the model-list request succeeded.
- `error`: a sanitized error message, or `null`.

For Azure, the selected model is the Azure deployment name.

## `POST /api/tasks`

Creates and starts a background browser-test run.

### Request body

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `configuration` | string | yes | Configuration ID from `/api/configurations`. |
| `provider` | `"vllm"`, `"azure"`, or `"openai"` | yes | Vendor to use. |
| `model` | string | yes | Model ID, or Azure deployment name. |
| `task` | string | yes | Natural-language or Gherkin test instructions. |
| `base_url` | string or `null` | no | URL opened before the run. Defaults to `null`. |
| `num_task_executions` | integer | no | Complete repetitions, from 1 to 20. Defaults to `1`. |
| `max_iterations` | integer | no | Agent-loop limit per execution, from 1 to 500. Defaults to `50`. |
| `vision_enabled` | boolean | no | Whether the browser agent uses screenshots. Defaults to `true`. |
| `record_video` | boolean | no | Save a browser recording at 5 frames per second with the task. Defaults to `false`. |

The provider credentials and endpoint are always read from the backend
environment. The frontend sends only the provider and model selected by the
user. When the demo launcher is used, the available models are additionally
filtered by its JSON allowlist, and models not listed there are rejected.
When `DEMO_SAFETY_GUARD` is enabled, each request is checked by the fail-closed
safety classifier before a task record is created. Unsafe tasks return `400`;
if classification is unavailable, the request returns `503` and no task is
started. The Windows and Linux demo launchers enable this setting automatically.

### Example request

```bash
curl -X POST http://localhost:8000/api/tasks ^
  -H "Content-Type: application/json" ^
  -d "{\"configuration\":\"BrowserOnlyConfiguration\",\"provider\":\"vllm\",\"model\":\"RedHatAI/gemma-4-31B-it-FP8-Dynamic\",\"task\":\"Navigate to the owners search page. Search for the owner with last name Franklin. Verify that George Franklin appears in the results.\",\"base_url\":\"http://localhost:8080/\",\"num_task_executions\":1,\"max_iterations\":10,\"vision_enabled\":false}"
```

### Response `201`

The response is a full task detail object. The task normally starts with
`status: "pending"` and then changes to `"running"`.
Task responses include `record_video` and `video_available`. When recording is
complete, `GET /api/tasks/{task_id}/video` returns the MP4 file.

```json
{
  "id": "5305b25a-ed32-4676-8d4f-138094e6447a",
  "configuration": "BrowserOnlyConfiguration",
  "provider": "vllm",
  "model": "RedHatAI/gemma-4-31B-it-FP8-Dynamic",
  "task": "Navigate to the owners search page...",
  "base_url": "http://localhost:8080/",
  "status": "pending",
  "current_execution": 0,
  "num_task_executions": 1,
  "created_at": "2026-09-09T10:00:00Z",
  "updated_at": "2026-09-09T10:00:00Z",
  "error": null,
  "events": []
}
```

### Errors

- `400`: unknown configuration, missing provider configuration, or invalid
  model/provider selection.
- `422`: request validation failed, for example a missing required field or a
  value outside the allowed range.

Example:

```json
{
  "detail": "Provider 'vllm' is not configured (VLLM_BASE_URL is missing)"
}
```

## `GET /api/tasks`

Returns all task runs, newest first. This endpoint returns summaries without
the event history.

### Response `200`

```json
[
  {
    "id": "5305b25a-ed32-4676-8d4f-138094e6447a",
    "configuration": "BrowserOnlyConfiguration",
    "provider": "vllm",
    "model": "RedHatAI/gemma-4-31B-it-FP8-Dynamic",
    "task": "Navigate to the owners search page...",
    "base_url": "http://localhost:8080/",
    "status": "running",
    "current_execution": 1,
    "num_task_executions": 1,
    "created_at": "2026-09-09T10:00:00Z",
    "updated_at": "2026-09-09T10:00:08Z",
    "error": null
  }
]
```

## `GET /api/tasks/stream`

Keeps a client informed when the task list changes using Server-Sent Events
(SSE). The frontend should load the initial list with `GET /api/tasks`, then
refresh it whenever it receives a `tasks_changed` event. The endpoint sends
keep-alive comments and supports automatic reconnection; clients should reload
the task list when the connection opens again to catch up on changes made while
disconnected.

### Event

```text
data: {"type":"tasks_changed"}
```

## `GET /api/tasks/{task_id}`

Returns one task summary plus all events, statistics, and the result recorded
so far.

### Response `200`

The response has the same task fields as the list endpoint and an additional
`events` array:

```json
{
  "id": "5305b25a-ed32-4676-8d4f-138094e6447a",
  "configuration": "FourAgentConfiguration",
  "provider": "vllm",
  "model": "RedHatAI/gemma-4-31B-it-FP8-Dynamic",
  "task": "Navigate to the owners search page...",
  "base_url": "http://localhost:8080/",
  "status": "completed",
  "current_execution": 1,
  "num_task_executions": 1,
  "max_iterations": 50,
  "vision_enabled": false,
  "created_at": "2026-09-09T10:00:00Z",
  "updated_at": "2026-09-09T10:00:22Z",
  "error": null,
  "statistics": {
    "iterations": 2,
    "llm_calls": 8,
    "tokens_by_agent": {},
    "tokens_total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
  },
  "result": {"message": "Test completed", "passed": true},
  "events": [
    {
      "type": "step_start",
      "data": {"step": 1},
      "timestamp": 1788948022.12,
      "execution_index": 1
    }
  ]
}
```

Returns `404` when the task ID does not exist:

```json
{
  "detail": "Task not found"
}
```

## `GET /api/tasks/{task_id}/stream`

Streams task events using Server-Sent Events (SSE). The stream:

1. Replays events already recorded.
2. Waits for and sends new events while the task runs.
3. Sends a final `done` event after the task finishes.

The event data is JSON. Events do not use a named SSE event except for the
final `done` message.

### Example

```bash
curl -N http://localhost:8000/api/tasks/5305b25a-ed32-4676-8d4f-138094e6447a/stream
```

### Event format

```text
data: {"type":"step_start","data":{"step":1},"timestamp":1788948022.12,"execution_index":1}

data: {"type":"agent_decision","data":{"step":1,"agent":"browser","decision_type":"continue","payload":"..."},"timestamp":1788948023.10,"execution_index":1}

event: done
data: {}
```

### Event types

| Type | Meaning | Typical `data` |
| --- | --- | --- |
| `step_start` | An agent-loop step started. | `{ "step": 1 }` |
| `agent_decision` | An agent produced a decision. | `step`, `agent`, `decision_type`, `payload` |
| `step_complete` | All agents for the step finished. | `{ "step": 1 }` |
| `completed` | The browser agent reported successful completion. | `{ "step": 1 }` |
| `stopped` | An agent requested that the run stop. | `{ "step": 1 }` |
| `max_iterations` | The configured loop limit was reached. | `{ "step": 51 }` |
| `error` | Reserved event type for an execution error. | Error-specific data |

For repeated runs, `execution_index` identifies which repetition produced the
event. It starts at `1`.

### Frontend JavaScript example

```js
const source = new EventSource(`/api/tasks/${taskId}/stream`);

source.onmessage = (event) => {
  const agentEvent = JSON.parse(event.data);
  renderAgentEvent(agentEvent);
};

source.addEventListener("done", () => {
  source.close();
  refreshTask(taskId);
});

source.onerror = () => {
  source.close();
  refreshTask(taskId);
};
```

## `GET /api/tasks/{task_id}/browser-stream`

When `DEMO_BROWSER_STREAMING` is enabled, streams the task's browser as an
MJPEG response (`multipart/x-mixed-replace`). This includes the browser-use
configurations and AutoGen Playwright (which publishes viewport screenshots).
Frames are not added to task event history. The demo launchers enable browser
streaming by default.

## `DELETE /api/tasks/{task_id}`

Requests cancellation of a running task.

### Response when cancelled

```json
{
  "cancelled": true
}
```

### Response when already finished

```json
{
  "cancelled": false,
  "reason": "Task already finished"
}
```

Returns `404` if the task ID does not exist.

## `DELETE /api/tasks`

Stops any active non-archived tasks and deletes all persisted non-archived task
records and screenshots. Archived tasks are preserved. The response contains
the number of removed tasks:

```json
{
  "deleted": 3
}
```

## `PATCH /api/tasks/{task_id}/archive`

Sets the archive state for a task. Pass `archived=false` to unarchive it.

## Recommended frontend flow

1. Call `/api/configurations` and `/api/models` when the configuration screen
   opens.
2. Show only models where `reachable` is `true`, or show the provider error
   when a configured provider is unavailable.
3. Submit the selected configuration, provider, model, task, and run options to
   `/api/tasks`.
4. Store the returned task `id`.
5. Open `/api/tasks/{id}/stream` for live progress.
6. Use `/api/tasks/{id}` to refresh/replay a run or recover after reconnecting.
7. Use `DELETE /api/tasks/{id}` for a stop button.
