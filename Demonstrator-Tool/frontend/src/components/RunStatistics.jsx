import React, { useState } from "react";
import { BarChart3, X } from "lucide-react";

function number(value) {
  return Number(value || 0).toLocaleString();
}

export default function RunStatistics({ statistics }) {
  const [open, setOpen] = useState(false);
  if (!statistics || Object.keys(statistics).length === 0) return null;

  const agents = Object.entries(statistics.tokens_by_agent || {});
  const total = statistics.tokens_total || {};

  return (
    <>
      <button className="at-stats-summary" onClick={() => setOpen(true)} type="button">
        <BarChart3 size={14} />
        <span>{number(statistics.iterations)} iterations</span>
        <span>·</span>
        <span>{number(statistics.llm_calls)} agent calls</span>
        <span>·</span>
        <span>{number(total.total_tokens)} tokens</span>
        <span className="at-stats-link">View details</span>
      </button>

      {open && (
        <div className="at-modal-backdrop" role="presentation" onClick={() => setOpen(false)}>
          <section
            className="at-stats-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Run statistics"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="at-stats-modal-head">
              <div>
                <div className="at-stats-modal-title">Run statistics</div>
                <div className="at-stats-modal-sub">Recorded metrics for this task</div>
              </div>
              <button className="at-modal-close" onClick={() => setOpen(false)} type="button" aria-label="Close">
                <X size={17} />
              </button>
            </div>

            <div className="at-stats-grid">
              <div><span>Iterations</span><strong>{number(statistics.iterations)}</strong></div>
              <div><span>Agent calls</span><strong>{number(statistics.llm_calls)}</strong></div>
              <div><span>Prompt tokens</span><strong>{number(total.prompt_tokens)}</strong></div>
              <div><span>Completion tokens</span><strong>{number(total.completion_tokens)}</strong></div>
              <div><span>Total tokens</span><strong>{number(total.total_tokens)}</strong></div>
            </div>

            <div className="at-stats-section-title">By agent</div>
            <div className="at-stats-table">
              <div className="at-stats-row at-stats-header">
                <span>Agent</span><span>Calls</span><span>Prompt</span><span>Completion</span><span>Total</span>
              </div>
              {agents.map(([agent, values]) => (
                <div className="at-stats-row" key={agent}>
                  <span>{agent}</span>
                  <span>{number(values.calls)}</span>
                  <span>{number(values.prompt_tokens)}</span>
                  <span>{number(values.completion_tokens)}</span>
                  <span>{number(values.total_tokens)}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
