# Backend

A FastAPI service for running and observing the multi-agent browser tests.

## Responsibilities

- Exposes the task and model-discovery API.
- Builds OpenAI, Azure OpenAI, or OpenAI-compatible/vLLM clients.
- Starts Chromium through `browser-use`.
- Runs the browser-only and four-agent configurations, plus the optional
  AutoGen Playwright configuration.
- Streams task events over Server-Sent Events.

## Backend structure

```text
backend/
├── agents/
│   ├── agents.py                 Agent base classes and agent implementations
│   ├── agent_configurations.py   Browser-only and four-agent configurations
│   ├── browser_manager.py        Chromium lifecycle and browser helpers
│   ├── factory.py                Provider/model discovery and builders
│   ├── loop.py                   Shared agent execution loop
│   ├── model_configuration.py    Provider client wrappers
│   ├── special_tools.py          Coordinator tools and stop handling
│   └── tools.py                  DOM inspection tools
├── events.py                     Progress event dataclass
├── main.py                       FastAPI application and routes
├── schemas.py                    Pydantic API models
├── task_manager.py               Background task execution and event storage
├── API.md                        Detailed API reference
└── pyproject.toml                Python dependencies
```

## Setup

From this directory:

```powershell
uv sync
uv run playwright install chromium
Copy-Item .env.example .env
```

Configure one or more providers in `.env`. Provider credentials and endpoints
remain server-side. Models are discovered at runtime and selected per task.

The AutoGen Playwright configuration is optional because its legacy AutoGen
dependency has additional native dependencies and requires Python 3.12 on
Windows. Enable it with:

```powershell
uv sync --extra autogen --python 3.12
uv run playwright install chromium
```

## Run

```powershell
uv run uvicorn main:app
```

The service is available at `http://localhost:8000`. Health and OpenAPI
endpoints are available at:

```text
GET http://localhost:8000/api/health
http://localhost:8000/docs
```

## Provider settings

OpenAI-compatible/vLLM:

```env
VLLM_BASE_URL=https://your-server.example/v1
VLLM_API_KEY=sk-your-token
```

Azure OpenAI:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_API_VERSION=2024-10-21
```

OpenAI:

```env
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=your-key
```

Use `GET /api/models` to inspect configured and reachable providers and their
available models.

## AutoGen Playwright configuration

`AutoGenPlaywrightConfiguration` is an isolated adapter for the legacy
AutoGen/Playwright approach. It launches a dedicated Chromium instance, asks
AutoGen agents to generate one Playwright action at a time, and reports the
conversation through the same task events as the browser-use configurations.

The executor runs generated Python scripts locally under `logs/` with Docker
disabled. Use this configuration only for trusted local demonstrations; it
must not be exposed to untrusted task submitters without a sandbox.

## API

See [API.md](API.md) for request schemas, responses, task lifecycle, and SSE
event details.
