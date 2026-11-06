import React from "react";
import { AlertTriangle, XCircle } from "lucide-react";
import { agentColor, formatTime } from "../utils/format.js";

export default function EventItem({ event }) {
  switch (event.type) {
    case "step_start":
      return (
        <div className="at-divider">
          Step {event.data?.step}
          {event.execution_index > 1 ? ` · execution ${event.execution_index}` : ""}
        </div>
      );

    case "step_complete":
      return <div className="at-complete-line">step {event.data?.step} complete</div>;

    case "stopped":
      return (
        <div className="at-callout warn">
          <AlertTriangle size={14} style={{ marginTop: 1, flexShrink: 0 }} />
          <div>
            Run stopped at step {event.data?.step}.
            {event.data?.reason ? ` ${event.data.reason}` : ""}
          </div>
        </div>
      );

    case "completed":
      return (
        <div className="at-callout info">
          <div>Run completed successfully at step {event.data?.step}.</div>
        </div>
      );

    case "max_iterations":
      return (
        <div className="at-callout warn">
          <AlertTriangle size={14} style={{ marginTop: 1, flexShrink: 0 }} />
          <div>Reached the maximum iteration limit at step {event.data?.step}.</div>
        </div>
      );

    case "error":
      return (
        <div className="at-callout error">
          <XCircle size={14} style={{ marginTop: 1, flexShrink: 0 }} />
          <pre>{JSON.stringify(event.data, null, 2)}</pre>
        </div>
      );

    case "agent_decision": {
      const agent = event.data?.agent || "agent";
      const payload = event.data?.payload;
      return (
        <div className="at-event-row">
          <div className="at-agent-tag" style={{ color: agentColor(agent) }}>
            {agent}
          </div>
          <div className="at-event-body">
            <div className="at-event-body-top">
              {event.data?.decision_type && (
                <span className="at-decision-type">{event.data.decision_type}</span>
              )}
              <span className="at-event-time">{formatTime(event.timestamp)}</span>
            </div>
            <div className="at-payload">
              {typeof payload === "string" ? payload : JSON.stringify(payload, null, 2)}
            </div>
          </div>
        </div>
      );
    }

    default:
      return (
        <div className="at-callout info">
          <pre>{JSON.stringify(event, null, 2)}</pre>
        </div>
      );
  }
}
