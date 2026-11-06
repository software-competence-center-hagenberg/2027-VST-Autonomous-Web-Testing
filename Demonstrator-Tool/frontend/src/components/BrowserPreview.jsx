import React, { useEffect, useState } from "react";

export default function BrowserPreview({ task, apiBase }) {
  const [unavailable, setUnavailable] = useState(false);
  const streamUrl = task
    ? `${apiBase.replace(/\/$/, "")}/api/tasks/${task.id}/browser-stream`
    : null;

  useEffect(() => {
    setUnavailable(false);
  }, [streamUrl]);

  useEffect(() => {
    if (task?.status === "running") setUnavailable(false);
  }, [task?.status]);

  return (
    <aside className="at-browser-preview">
      <div className="at-browser-preview-header">
        <span>Live browser</span>
        {task?.status === "running" && <span className="at-browser-live-indicator">LIVE</span>}
      </div>
      <div className="at-browser-preview-screen">
        {!task && <div className="at-browser-preview-empty">Start or select a task to view the browser.</div>}
        {task && unavailable && (
          <div className="at-browser-preview-empty">No browser preview is available for this task.</div>
        )}
        {task && !unavailable && (
          <img
            key={`${streamUrl}:${task.status}`}
            src={streamUrl}
            alt="Live view of the task browser"
            onError={() => setUnavailable(true)}
          />
        )}
      </div>
    </aside>
  );
}
