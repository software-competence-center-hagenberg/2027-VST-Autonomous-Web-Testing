import { useCallback, useEffect, useRef, useState } from "react";

// Uses a task-change event stream to keep the sidebar current, and exposes a
// manual refresh + optimistic prepend for right after a POST /api/tasks.
export function useTaskList(apiClient) {
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState(null);
  const refreshTimerRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const data = await apiClient.getTasks();
      setTasks(data);
      setError(null);
    } catch (e) {
      setError(e.message || "Could not load runs.");
    }
  }, [apiClient]);

  const prepend = useCallback((task) => {
    setTasks((prev) => [task, ...prev.filter((t) => t.id !== task.id)]);
  }, []);

  useEffect(() => {
    refresh();
    const events = new EventSource(apiClient.taskChangesUrl());
    const scheduleRefresh = () => {
      if (refreshTimerRef.current !== null) {
        clearTimeout(refreshTimerRef.current);
      }
      refreshTimerRef.current = setTimeout(() => {
        refreshTimerRef.current = null;
        refresh();
      }, 50);
    };

    events.onopen = refresh;
    events.onmessage = scheduleRefresh;

    return () => {
      events.close();
      if (refreshTimerRef.current !== null) {
        clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = null;
      }
    };
  }, [apiClient, refresh]);

  return { tasks, error, refresh, prepend };
}
