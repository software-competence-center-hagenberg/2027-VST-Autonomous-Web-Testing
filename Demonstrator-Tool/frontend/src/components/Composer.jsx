import React, { useLayoutEffect, useRef } from "react";
import { ChevronDown, ChevronRight, ArrowUp, Loader2 } from "lucide-react";
import { summarizeSettings } from "../utils/format.js";
import SettingsPanel from "./SettingsPanel.jsx";

export default function Composer({
  form,
  onFormChange,
  settingsOpen,
  onToggleSettings,
  configurations,
  models,
  modelsLoaded,
  onSubmit,
  submitting,
  submitError,
}) {
  const textareaRef = useRef(null);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
    textarea.style.overflowY = textarea.scrollHeight > 160 ? "auto" : "hidden";
  }, [form.task]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <div className="at-composer">
      <button className="at-settings-toggle" onClick={onToggleSettings}>
        {settingsOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        Run settings — {summarizeSettings(form)}
      </button>

      {settingsOpen && (
        <SettingsPanel
          form={form}
          onChange={onFormChange}
          configurations={configurations}
          models={models}
          modelsLoaded={modelsLoaded}
        />
      )}

      <div className="at-composer-input-row">
        <textarea
          ref={textareaRef}
          className="at-composer-textarea"
          placeholder="Describe what the agents should do, e.g. Navigate to the owners search page and find Franklin…"
          rows={1}
          value={form.task}
          onChange={(e) => onFormChange({ ...form, task: e.target.value })}
          onKeyDown={handleKeyDown}
        />
        <button
          className="at-send-btn"
          onClick={onSubmit}
          disabled={submitting || !form.task.trim()}
          title="Start run"
        >
          {submitting ? <Loader2 size={15} className="at-spin" /> : <ArrowUp size={16} />}
        </button>
      </div>
      {submitError && <div className="at-submit-error">{submitError}</div>}
    </div>
  );
}
