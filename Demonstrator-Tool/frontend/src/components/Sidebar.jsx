import React, { useState } from "react";
import { Plus, Circle, RotateCcw, Play, SlidersHorizontal, Trash2, Archive, ArchiveRestore } from "lucide-react";
import { statusMeta, shortId, formatTime } from "../utils/format.js";

function RunHistoryItem({
  task,
  active,
  touchMode,
  onSelect,
  onReplay,
  onLoadSettings,
  onToggleArchived,
}) {
  const meta = statusMeta(task.status);
  const replayable = task.status !== "running" && task.status !== "pending";
  return (
    <div className={`at-run-item ${active ? "active" : ""}`}>
      <button className="at-run-item-select" onClick={onSelect}>
        <div className="at-run-item-top">
          <Circle size={7} fill={meta.color} color={meta.color} />
          <span className="at-run-id">{shortId(task.id)}</span>
          <span className="at-run-id" style={{ marginLeft: "auto" }}>
            {formatTime(task.updated_at)}
          </span>
        </div>
        <div className="at-run-task">{task.task}</div>
      </button>
      <div className="at-run-actions">
        {replayable && (
          <button
            className="at-replay-btn"
            type="button"
            onClick={() => onReplay(task)}
            title="Replay task"
            aria-label="Replay task"
          >
            {touchMode ? <Play size={15} /> : <RotateCcw size={13} />}
            {touchMode && <span>Replay</span>}
          </button>
        )}
        {!touchMode && (
          <>
            <button
              className="at-archive-btn"
              type="button"
              onClick={() => void onToggleArchived(task)}
              title={task.archived ? "Unarchive task" : "Archive task"}
              aria-label={task.archived ? "Unarchive task" : "Archive task"}
            >
              {task.archived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
            </button>
            <button
              className="at-load-settings-btn"
              type="button"
              onClick={() => onLoadSettings(task)}
              title="Load task settings"
              aria-label="Load task settings"
            >
              <SlidersHorizontal size={13} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function Sidebar({
  tasks,
  selectedTaskId,
  touchMode = false,
  onSelectTask,
  onReplayTask,
  onLoadTaskSettings,
  onToggleArchived,
  onNewRun,
  onClearTasks,
  apiBase,
  onApiBaseChange,
  connError,
}) {
  const [draft, setDraft] = useState(apiBase);

  const save = () => onApiBaseChange(draft.trim());

  return (
    <aside className="at-sidebar">
      <div className="at-brand">
        <div className="at-brand-title">agent-console</div>
        <div className="at-brand-sub">browser-agent test runner</div>
      </div>

      {!touchMode && (
        <button className="at-new-run" onClick={onNewRun}>
          <Plus size={14} />
          New run
        </button>
      )}

      <div className="at-runs-label">
        <span>{touchMode ? "Example tasks" : "Recent runs"}</span>
        {!touchMode && tasks.length > 0 && (
          <button className="at-clear-tasks-btn" onClick={onClearTasks} type="button">
            <Trash2 size={12} />
            Clear
          </button>
        )}
      </div>
      <div className="at-runs-list">
        {tasks.length === 0 && (
          <div className="at-run-empty">
            {touchMode ? "No example tasks are available." : "No runs yet."}
          </div>
        )}
        {tasks.map((t) => (
          <RunHistoryItem
            key={t.id}
            task={t}
            active={t.id === selectedTaskId}
            touchMode={touchMode}
            onSelect={() => onSelectTask(t.id)}
            onReplay={() => onReplayTask(t)}
            onLoadSettings={onLoadTaskSettings}
            onToggleArchived={onToggleArchived}
          />
        ))}
      </div>

      {!touchMode && (
        <div className="at-apibase">
          <div className="at-apibase-label">API base URL</div>
          <div className="at-apibase-row">
            <input
              className="at-apibase-input"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && save()}
            />
            <button className="at-apibase-btn" onClick={save}>
              Set
            </button>
          </div>
          {connError && <div className="at-conn-error">{connError}</div>}
        </div>
      )}
    </aside>
  );
}
