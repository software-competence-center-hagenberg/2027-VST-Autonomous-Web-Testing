import React, { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { agentColor, formatTime } from "../utils/format.js";

function cleanText(value) {
  return String(value || "").replace(/\u001b\[[0-?]*[ -/]*[@-~]/g, "").trim();
}

export default function AgentCall({ decision, internalSteps, streaming, apiBase }) {
  const [expanded, setExpanded] = useState(streaming);
  const agent = decision?.data?.agent || internalSteps[0]?.data?.agent || "agent";
  const payload = decision?.data?.payload;
  const groupedSteps = new Map();
  internalSteps.forEach((event, index) => {
    const step = event.data?.internal_step ?? index + 1;
    const group = groupedSteps.get(step) || { events: [], screenshot: null };
    if (event.data?.kind === "screenshot") group.screenshot = event.data.screenshot;
    else group.events.push(event);
    groupedSteps.set(step, group);
  });
  const logSteps = [...groupedSteps.entries()];

  useEffect(() => {
    setExpanded(streaming);
  }, [streaming]);

  return (
    <div className="at-event-row">
      <div className="at-agent-tag" style={{ color: agentColor(agent) }}>{agent}</div>
      <div className="at-event-body">
        <div className="at-event-body-top">
          {decision?.data?.decision_type && (
            <span className="at-decision-type">{decision.data.decision_type}</span>
          )}
          <span className="at-event-time">
            {formatTime(decision?.timestamp || internalSteps[0]?.timestamp)}
          </span>
        </div>

        {internalSteps.length > 0 && (
          <div className="at-browser-details">
            <button
              className="at-browser-details-toggle"
              type="button"
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              <span>Browser-use steps ({logSteps.length})</span>
              {!decision && <span className="at-browser-running">running</span>}
            </button>
            {(expanded || streaming) && (
              <div className="at-browser-step-list">
                {logSteps.map(([step, group]) => (
                  <div className="at-browser-step" key={step}>
                    <div className="at-browser-step-heading">
                      <strong>Step {step}</strong>
                      <span>{group.events.length} browser-use updates</span>
                      {group.screenshot && (
                        <ScreenshotButton
                          screenshot={group.screenshot}
                          apiBase={apiBase}
                        />
                      )}
                    </div>
                    <div className="at-browser-step-lines">
                      {group.events.map((event, index) => (
                        <div key={`${event.timestamp}-${index}`}>
                          {cleanText(event.data?.text) || "Browser-use update"}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {decision && (
          <div className="at-payload">
            {typeof payload === "string" ? payload : JSON.stringify(payload, null, 2)}
          </div>
        )}
      </div>
    </div>
  );
}

function ScreenshotButton({ screenshot, apiBase }) {
  const [open, setOpen] = useState(false);
  const url = `${apiBase.replace(/\/$/, "")}${screenshot.url}`;
  return (
    <>
      <button
        className="at-screenshot-btn"
        type="button"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setOpen(true);
        }}
      >
        View screenshot
      </button>
      {open && (
        <div className="at-screenshot-backdrop" onClick={() => setOpen(false)}>
          <div className="at-screenshot-modal" onClick={(event) => event.stopPropagation()}>
            <button className="at-screenshot-close" type="button" onClick={() => setOpen(false)}>Close</button>
            <img src={url} alt={`Browser state after step ${screenshot.filename}`} />
          </div>
        </div>
      )}
    </>
  );
}
