import { STATUS_META, AGENT_COLORS } from "../constants.js";

export function statusMeta(status) {
  return STATUS_META[status] || { label: status || "Unknown", color: "#838C9C" };
}

export function agentColor(agent) {
  const key = String(agent || "").toLowerCase();
  return AGENT_COLORS[key] || "#9AA5B8";
}

export function shortId(id) {
  return id ? id.slice(0, 8) : "";
}

export function formatTime(input) {
  if (!input) return "";
  try {
    const d = typeof input === "number" ? new Date(input * 1000) : new Date(input);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return String(input);
  }
}

export function summarizeSettings(form) {
  const exec = `${form.num_task_executions}× execution${Number(form.num_task_executions) > 1 ? "s" : ""}`;
  const iter = `${form.max_iterations} steps max`;
  const vision = form.vision_enabled ? "vision on" : "vision off";
  const video = form.record_video ? "video on" : "video off";
  const model = form.model ? `${form.provider}/${form.model}` : "no model selected";
  return `${model} · ${exec} · ${iter} · ${vision} · ${video}`;
}
