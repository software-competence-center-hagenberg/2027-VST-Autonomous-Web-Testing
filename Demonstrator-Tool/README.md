# Autonomous Web Testing Demonstrator

A local demonstration platform for LLM-driven web testing. It combines a
FastAPI backend that runs and observes browser-testing tasks, a React/Vite
frontend for selecting configurations and models and watching agent events
live, and `browser-use` with Chromium for real browser automation.

The backend supports several agent configurations, including a single
browser-only agent and multi-agent setups, and can connect to OpenAI, Azure
OpenAI, or any OpenAI-compatible (e.g. vLLM) model provider.

## Repository layout

```text
.
├── backend/          FastAPI service and multi-agent browser runner
├── frontend/         React/Vite monitoring and task-submission UI
├── start-demo.ps1    Windows launcher for the complete demonstration
├── start-demo.sh     Linux launcher for the complete demonstration
└── demo-models.json  Models enabled by the demo launcher
```

## Prerequisites

- Python 3.11 or newer, with `uv` for backend dependencies.
- Node.js 18 or newer and npm.
- Chromium installed for `browser-use`.
- Access to at least one supported LLM provider.

## Setup

1. Copy the backend environment template and fill in your provider
   credentials:

   ```bash
   cp backend/.env.example backend/.env
   ```

   Edit `backend/.env` and set at least one provider (vLLM/OpenAI-compatible,
   Azure OpenAI, or OpenAI). Models are discovered at runtime, so no model
   names are configured here.

2. Install the backend and frontend dependencies:

   ```bash
   cd backend
   uv sync --extra autogen --python 3.12
   uv run playwright install chromium
   cd ../frontend
   npm install
   cd ..
   ```

3. Run the demonstration. Either use the launcher, which starts the backend
   and frontend and opens the UI:

   ```powershell
   .\start-demo.ps1        # Windows
   ```

   ```bash
   ./start-demo.sh         # Linux
   ```

   or run the two services yourself in separate terminals:

   ```bash
   # Backend
   cd backend
   uv run uvicorn main:app
   ```

   ```bash
   # Frontend
   cd frontend
   npm run dev
   ```

   Then open `http://localhost:5173`. The backend API defaults to
   `http://localhost:8000`.

## Documentation

- Interactive OpenAPI documentation: `http://localhost:8000/docs`
- Backend API reference: [backend/API.md](backend/API.md)
- Backend notes: [backend/README.md](backend/README.md)
- Frontend notes: [frontend/README.md](frontend/README.md)
