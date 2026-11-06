import React from "react";

export default function SettingsPanel({ form, onChange, configurations, models, modelsLoaded }) {
  const providerOptions = Object.entries(models).filter(
    ([, v]) => v.configured && v.reachable && v.models.length
  );
  const configMeta = configurations.find((c) => c.id === form.configuration);

  const set = (patch) => onChange({ ...form, ...patch });

  return (
    <div className="at-settings-panel">
      <div className="at-field">
        <label>Configuration</label>
        <select value={form.configuration} onChange={(e) => set({ configuration: e.target.value })}>
          {configurations.map((c) => (
            <option key={c.id} value={c.id}>
              {c.display_name}
            </option>
          ))}
        </select>
        {configMeta && <div className="at-field-help">Agents: {configMeta.agents.join(", ")}</div>}
      </div>

      <div className="at-field">
        <label>Provider</label>
        <select
          value={form.provider}
          onChange={(e) => {
            const provider = e.target.value;
            const firstModel = models[provider]?.models?.[0] || "";
            set({ provider, model: firstModel });
          }}
        >
          <option value="">{modelsLoaded ? "Select a provider" : "Loading…"}</option>
          {providerOptions.map(([key]) => (
            <option key={key} value={key}>
              {key}
            </option>
          ))}
        </select>
        {modelsLoaded && providerOptions.length === 0 && (
          <div className="at-provider-warning">No provider is both configured and reachable.</div>
        )}
      </div>

      <div className="at-field">
        <label>Model</label>
        <select
          value={form.model}
          onChange={(e) => set({ model: e.target.value })}
          disabled={!form.provider}
        >
          {(models[form.provider]?.models || []).map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
      </div>

      <div className="at-field">
        <label>Base URL (page to open)</label>
        <input
          type="text"
          placeholder="http://localhost:8080/"
          value={form.base_url}
          onChange={(e) => set({ base_url: e.target.value })}
        />
      </div>

      <div className="at-field">
        <label>Executions (1–20)</label>
        <input
          type="number"
          min={1}
          max={20}
          value={form.num_task_executions}
          onChange={(e) => set({ num_task_executions: e.target.value })}
        />
      </div>

      <div className="at-field">
        <label>Max iterations (1–500)</label>
        <input
          type="number"
          min={1}
          max={500}
          value={form.max_iterations}
          onChange={(e) => set({ max_iterations: e.target.value })}
        />
      </div>

      <div className="at-field-full at-checkbox-row">
        <input
          type="checkbox"
          id="vision"
          checked={form.vision_enabled}
          onChange={(e) => set({ vision_enabled: e.target.checked })}
        />
        <label htmlFor="vision">Vision enabled (browser agent uses screenshots)</label>
      </div>
      <div className="at-field-full at-checkbox-row">
        <input
          type="checkbox"
          id="record-video"
          checked={form.record_video}
          onChange={(e) => set({ record_video: e.target.checked })}
        />
        <label htmlFor="record-video">Record browser video (MP4)</label>
      </div>
    </div>
  );
}
