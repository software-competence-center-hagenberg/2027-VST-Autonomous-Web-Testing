import React, { useEffect, useRef, useState } from "react";
import { ArrowDown, Film, Gauge, XCircle } from "lucide-react";
import EventItem from "./EventItem.jsx";
import RunStatistics from "./RunStatistics.jsx";
import AgentCall from "./AgentCall.jsx";

export default function Transcript({ selectedTaskId, transcript, streaming, task, apiBase, touchMode = false }) {
  const transcriptRef = useRef(null);
  const endRef = useRef(null);
  const userScrollIntentRef = useRef(false);
  const scrollIntentTimeoutRef = useRef(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const taskFinished = ["completed", "failed", "stopped"].includes(task?.status);

  useEffect(() => {
    setIsAtBottom(true);
  }, [selectedTaskId]);

  useEffect(() => {
    if (isAtBottom) {
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [isAtBottom, selectedTaskId, transcript, streaming, task?.status, task?.video_available]);

  useEffect(
    () => () => window.clearTimeout(scrollIntentTimeoutRef.current),
    []
  );

  const markUserScrollIntent = () => {
    userScrollIntentRef.current = true;
    window.clearTimeout(scrollIntentTimeoutRef.current);
    scrollIntentTimeoutRef.current = window.setTimeout(() => {
      userScrollIntentRef.current = false;
    }, 300);
  };

  const handleScroll = () => {
    if (!userScrollIntentRef.current || !transcriptRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = transcriptRef.current;
    setIsAtBottom(scrollHeight - scrollTop - clientHeight <= 32);
  };

  const scrollToBottom = () => {
    userScrollIntentRef.current = false;
    window.clearTimeout(scrollIntentTimeoutRef.current);
    setIsAtBottom(true);
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
  };

  if (!selectedTaskId) {
    return (
      <div className="at-transcript-shell">
        <div className="at-transcript">
          <div className="at-empty-state">
            <div className="at-empty-state-title">{touchMode ? "Choose an example" : "No run selected"}</div>
            <div className="at-empty-state-sub">
              {touchMode
                ? "Select a task in the sidebar to see the agent conversation and browser."
                : "Pick a configuration and model below, describe what the agents should do, and send it to watch the run happen live."}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="at-transcript-shell">
      <div
        ref={transcriptRef}
        className="at-transcript"
        role="log"
        aria-label="Agent conversation"
        tabIndex={0}
        onScroll={handleScroll}
        onWheel={markUserScrollIntent}
        onTouchMove={markUserScrollIntent}
        onPointerDown={markUserScrollIntent}
        onPointerUp={markUserScrollIntent}
        onKeyDown={(event) => {
          if (["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Home", "End", " "].includes(event.key)) {
            markUserScrollIntent();
          }
        }}
      >
        {transcript.length === 0 && (
          <div className="at-empty-state">
            <div className="at-empty-state-title">
              {streaming ? "Waiting for the first event…" : "No events recorded."}
            </div>
          </div>
        )}

        {(() => {
          const calls = new Map();
          transcript.forEach((event, index) => {
            if (event.type !== "agent_decision" && event.type !== "browser_internal_step") return;
            const data = event.data || {};
            const callId = data.call_id || `${data.step}:${data.agent}`;
            const call = calls.get(callId) || { firstIndex: index, decision: null, internalSteps: [] };
            if (event.type === "agent_decision") call.decision = event;
            else call.internalSteps.push(event);
            calls.set(callId, call);
          });
          const renderedCalls = new Set();
          return transcript.map((event, index) => {
            if (event.type === "agent_decision" || event.type === "browser_internal_step") {
              const data = event.data || {};
              const callId = data.call_id || `${data.step}:${data.agent}`;
              const call = calls.get(callId);
              if (renderedCalls.has(callId) || call.firstIndex !== index) return null;
              renderedCalls.add(callId);
              return (
                <AgentCall
                  key={`call-${callId}`}
                  decision={call.decision}
                  internalSteps={call.internalSteps}
                  streaming={streaming}
                  apiBase={apiBase}
                />
              );
            }
            return <EventItem key={index} event={event} />;
          });
        })()}

        {task?.error && (
          <div className="at-callout error">
            <XCircle size={14} style={{ marginTop: 1, flexShrink: 0 }} />
            <div>{task.error}</div>
          </div>
        )}

        {!streaming && task?.statistics && <RunStatistics statistics={task.statistics} />}

        {taskFinished && !streaming && task?.video_available && (
          <TaskVideoButton taskId={task.id} apiBase={apiBase} />
        )}

        <div ref={endRef} />
      </div>
      {!isAtBottom && (
        <button
          className="at-scroll-to-bottom"
          type="button"
          onClick={scrollToBottom}
          aria-label="Scroll to latest message"
          title="Scroll to latest message"
        >
          <ArrowDown size={20} />
        </button>
      )}
    </div>
  );
}

function TaskVideoButton({ taskId, apiBase }) {
  const [open, setOpen] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(3);
  const videoRef = useRef(null);
  const url = `${apiBase.replace(/\/$/, "")}/api/tasks/${taskId}/video`;

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.playbackRate = playbackRate;
    }
  }, [open, playbackRate]);

  return (
    <>
      <button className="at-stats-summary at-video-summary" type="button" onClick={() => setOpen(true)}>
        <Film size={14} />
        <span>Browser recording</span>
        <span className="at-stats-link">Watch video</span>
      </button>
      {open && (
        <div className="at-screenshot-backdrop" onClick={() => setOpen(false)}>
          <div className="at-screenshot-modal" onClick={(event) => event.stopPropagation()}>
            <button className="at-screenshot-close" type="button" onClick={() => setOpen(false)}>Close</button>
            <label className="at-video-speed-control">
              <Gauge size={15} />
              <span>Playback speed</span>
              <select
                value={playbackRate}
                onChange={(event) => setPlaybackRate(Number(event.target.value))}
              >
                {[0.5, 1, 1.5, 2, 3, 4].map((rate) => (
                  <option key={rate} value={rate}>{rate}×</option>
                ))}
              </select>
            </label>
            <video
              ref={videoRef}
              src={url}
              controls
              autoPlay
              playsInline
              onLoadedMetadata={(event) => {
                event.currentTarget.playbackRate = playbackRate;
              }}
            />
          </div>
        </div>
      )}
    </>
  );
}
