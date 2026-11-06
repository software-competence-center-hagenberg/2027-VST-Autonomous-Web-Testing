export const DEFAULT_API_BASE = import.meta.env.VITE_API_BASE || "";

export const STATUS_META = {
  pending: { label: "Pending", color: "#838C9C" },
  running: { label: "Running", color: "#E1A94C" },
  completed: { label: "Completed", color: "#6FCF97" },
  failed: { label: "Failed", color: "#E5676B" },
  error: { label: "Error", color: "#E5676B" },
  cancelled: { label: "Cancelled", color: "#838C9C" },
};

export const AGENT_COLORS = {
  analyst: "#8AB4F8",
  coordinator: "#C792EA",
  browser: "#E1A94C",
  observer: "#6FCF97",
  coder: "#F28B82",
  executor: "#78D6C6",
  manager: "#B0BEC5",
};

export const DEFAULT_FORM = {
  configuration: "",
  provider: "",
  model: "",
  task: "",
  base_url: "",
  num_task_executions: 1,
  max_iterations: 50,
  vision_enabled: true,
  record_video: true,
};
