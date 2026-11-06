// Thin wrapper around the Agent Testing API described in API.md.
// Every function returns a Promise and throws an Error with a readable
// message on non-2xx responses, so callers only need one try/catch.

export function createApiClient(baseUrl) {
  const base = baseUrl.replace(/\/$/, "");

  async function request(path, options) {
    const res = await fetch(`${base}${path}`, options);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const detail = body.detail;
      const message = typeof detail === "string"
        ? detail
        : detail?.reason
          ? `${detail.message || "Request rejected"}: ${detail.reason}`
          : detail?.message || `HTTP ${res.status}`;
      throw new Error(message);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  return {
    baseUrl: base,

    getHealth: () => request("/api/health"),

    getConfigurations: () => request("/api/configurations"),

    getModels: () => request("/api/models"),

    getTasks: () => request("/api/tasks"),

    getTask: (taskId) => request(`/api/tasks/${taskId}`),

    createTask: (payload) =>
      request("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),

    cancelTask: (taskId) => request(`/api/tasks/${taskId}`, { method: "DELETE" }),
    clearTasks: () => request("/api/tasks", { method: "DELETE" }),
    setTaskArchived: (taskId, archived) =>
      request(`/api/tasks/${taskId}/archive?archived=${archived}`, { method: "PATCH" }),

    // Not a fetch call — EventSource needs a plain URL string.
    streamUrl: (taskId) => `${base}/api/tasks/${taskId}/stream`,
    taskChangesUrl: () => `${base}/api/tasks/stream`,
  };
}
