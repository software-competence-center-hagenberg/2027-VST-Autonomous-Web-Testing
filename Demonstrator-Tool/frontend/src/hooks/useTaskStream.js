import { useCallback, useEffect, useRef, useState } from "react";

// Owns a single EventSource at a time against GET /api/tasks/{id}/stream.
// The endpoint replays recorded events then streams live ones, so opening
// it works the same way whether the run is still going or already finished.
export function useTaskStream(apiClient) {
  const [transcript, setTranscript] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const esRef = useRef(null);
  const pendingEventsRef = useRef([]);
  const flushFrameRef = useRef(null);

  const discardPendingEvents = useCallback(() => {
    if (flushFrameRef.current !== null) {
      cancelAnimationFrame(flushFrameRef.current);
      flushFrameRef.current = null;
    }
    pendingEventsRef.current = [];
  }, []);

  const flushPendingEvents = useCallback(() => {
    if (flushFrameRef.current !== null) {
      cancelAnimationFrame(flushFrameRef.current);
      flushFrameRef.current = null;
    }
    const pending = pendingEventsRef.current;
    pendingEventsRef.current = [];
    if (pending.length > 0) {
      setTranscript((previous) => previous.concat(pending));
    }
  }, []);

  const closeStream = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    discardPendingEvents();
    setStreaming(false);
  }, [discardPendingEvents]);

  const openStream = useCallback(
    (taskId, onDone) => {
      closeStream();
      setTranscript([]);
      setStreaming(true);

      const es = new EventSource(apiClient.streamUrl(taskId));
      esRef.current = es;

      es.onmessage = (event) => {
        try {
          pendingEventsRef.current.push(JSON.parse(event.data));
          if (flushFrameRef.current === null) {
            flushFrameRef.current = requestAnimationFrame(() => {
              flushFrameRef.current = null;
              if (esRef.current === es) {
                flushPendingEvents();
              }
            });
          }
        } catch {
          // malformed frame — skip it rather than break the stream
        }
      };

      es.addEventListener("done", () => {
        flushPendingEvents();
        closeStream();
        onDone?.();
      });

      es.onerror = () => {
        flushPendingEvents();
        closeStream();
        onDone?.();
      };
    },
    [apiClient, closeStream, flushPendingEvents]
  );

  useEffect(() => () => closeStream(), [closeStream]);

  return { transcript, streaming, openStream, closeStream };
}
