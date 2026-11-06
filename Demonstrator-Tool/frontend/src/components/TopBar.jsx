import React from "react";
import { Square } from "lucide-react";
import { statusMeta } from "../utils/format.js";

export default function TopBar({ task, onStop, touchMode = false }) {
  return (
    <div className="at-topbar">
      <div className="at-topbar-left">
        <div className="at-topbar-title">{task ? task.task : touchMode ? "Select a demo" : "New run"}</div>
        <div className="at-topbar-meta">
          {task
            ? `${task.configuration} · ${task.provider}/${task.model} · execution ${task.current_execution}/${task.num_task_executions}`
            : touchMode
              ? "Choose an example from the sidebar to view or replay it"
              : "describe a task below to start a run"}
        </div>
      </div>

      {task && (
        <div style={{ display: "flex", alignItems: "center", flexShrink: 0 }}>
          <span className="at-status-pill" style={{ color: statusMeta(task.status).color }}>
            <span
              className={`at-status-dot ${task.status === "running" ? "pulse" : ""}`}
              style={{ background: statusMeta(task.status).color }}
            />
            {statusMeta(task.status).label}
          </span>
          {(task.status === "running" || task.status === "pending") && (
            <button className="at-stop-btn" onClick={onStop}>
              <Square size={12} />
              Stop
            </button>
          )}
        </div>
      )}
    </div>
  );
}
