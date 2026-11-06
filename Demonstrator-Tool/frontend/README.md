# Frontend

A chat-style frontend for the Agent Testing API: pick a configuration,
provider, and model, describe a task, and watch the agents' event stream
live.

## Requirements

- Node.js 18+
- The backend running and reachable (defaults to `http://localhost:8000`)

## Run it

```bash
npm install
npm run dev
```

Then open the URL Vite prints (usually `http://localhost:5173`).

If your backend isn't at `http://localhost:8000`, change the **API base
URL** field at the bottom of the sidebar.

