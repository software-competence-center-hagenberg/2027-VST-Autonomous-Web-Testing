import React, { useCallback, useEffect, useMemo, useState } from "react";
import "./App.css";
import { createApiClient } from "./api/client.js";
import { useTaskList } from "./hooks/useTaskList.js";
import { useTaskStream } from "./hooks/useTaskStream.js";
import { DEFAULT_API_BASE, DEFAULT_FORM } from "./constants.js";
import Sidebar from "./components/Sidebar.jsx";
import TopBar from "./components/TopBar.jsx";
import Transcript from "./components/Transcript.jsx";
import Composer from "./components/Composer.jsx";
import BrowserPreview from "./components/BrowserPreview.jsx";

export default function App() {
  const touchEnabled = new URLSearchParams(window.location.search)
    .get("touchenabled")
    ?.toLowerCase() === "true";
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const apiClient = useMemo(() => createApiClient(apiBase), [apiBase]);

  const [connError, setConnError] = useState(null);
  const [configurations, setConfigurations] = useState([]);
  const [models, setModels] = useState({});
  const [modelsLoaded, setModelsLoaded] = useState(false);

  const [selectedTaskId, setSelectedTaskId] = useState(null);
  const [selectedTaskDetail, setSelectedTaskDetail] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const { tasks, prepend, refresh: refreshTasks } = useTaskList(apiClient);
  const { transcript, streaming, openStream, closeStream } = useTaskStream(apiClient);

  const selectedTask = tasks.find((t) => t.id === selectedTaskId) || null;
  const transcriptTask = selectedTaskDetail?.id === selectedTaskId
    ? {
        ...selectedTask,
        ...selectedTaskDetail,
        video_available: selectedTaskDetail.video_available || selectedTask?.video_available || false,
      }
    : selectedTask;
  const browserStreamingEnabled = import.meta.env.VITE_BROWSER_STREAMING === "true";

  // Load configurations and models whenever the API base changes.
  useEffect(() => {
    let cancelled = false;

    apiClient
      .getConfigurations()
      .then((data) => {
        if (cancelled) return;
        setConfigurations(data);
        setConnError(null);
        setForm((f) => (f.configuration ? f : { ...f, configuration: data[0]?.id || "" }));
      })
      .catch((error) => {
        if (!cancelled) setConnError(error.message || "Could not load configurations.");
      });

    apiClient
      .getModels()
      .then((data) => {
        if (cancelled) return;
        setModels(data);
        setModelsLoaded(true);
        const firstUsable = Object.entries(data).find(
          ([, v]) => v.configured && v.reachable && v.models.length
        );
        if (firstUsable) {
          setForm((f) =>
            f.provider ? f : { ...f, provider: firstUsable[0], model: firstUsable[1].models[0] }
          );
        }
      })
      .catch(() => {
        if (!cancelled) setModelsLoaded(true);
      });

    return () => {
      cancelled = true;
    };
  }, [apiClient, apiBase]);

  const selectTask = useCallback(
    (taskId) => {
      setSelectedTaskId(taskId);
      setSelectedTaskDetail(null);
      apiClient.getTask(taskId).then(setSelectedTaskDetail).catch(() => {});
      openStream(taskId, () => {
        refreshTasks();
        apiClient.getTask(taskId).then(setSelectedTaskDetail).catch(() => {});
      });
    },
    [apiClient, openStream, refreshTasks]
  );

  useEffect(() => {
    if (touchEnabled && !submitting && !selectedTaskId && tasks.length > 0) {
      selectTask(tasks[0].id);
    }
  }, [selectTask, selectedTaskId, submitting, tasks, touchEnabled]);

  const startNewRun = useCallback(() => {
    closeStream();
    setSelectedTaskId(null);
    setSelectedTaskDetail(null);
    setSubmitError(null);
    setForm((f) => ({ ...f, task: "" }));
  }, [closeStream]);

  const replayTask = useCallback(
    async (task) => {
      setSubmitError(null);
      setSubmitting(true);
      closeStream();
      setSelectedTaskId(null);
      setSelectedTaskDetail(null);
      try {
        const replay = await apiClient.createTask({
          configuration: task.configuration,
          provider: task.provider,
          model: task.model,
          task: task.task,
          base_url: task.base_url,
          num_task_executions: task.num_task_executions,
          max_iterations: task.max_iterations,
          vision_enabled: task.vision_enabled,
          record_video: task.record_video,
        });
        prepend(replay);
        setSelectedTaskId(replay.id);
        setForm((current) => ({
          ...current,
          configuration: replay.configuration,
          provider: replay.provider,
          model: replay.model,
          base_url: replay.base_url || "",
          num_task_executions: replay.num_task_executions,
          max_iterations: replay.max_iterations,
          vision_enabled: replay.vision_enabled,
          record_video: replay.record_video,
          task: "",
        }));
        openStream(replay.id, () => {
          refreshTasks();
          apiClient.getTask(replay.id).then(setSelectedTaskDetail).catch(() => {});
        });
      } catch (e) {
        setSubmitError(e.message || "Could not replay the run.");
      } finally {
        setSubmitting(false);
      }
    },
    [apiClient, closeStream, prepend, openStream, refreshTasks]
  );

  const loadTaskSettings = useCallback((task) => {
    setForm((current) => ({
      ...current,
      configuration: task.configuration,
      provider: task.provider,
      model: task.model,
      base_url: task.base_url || "",
      num_task_executions: task.num_task_executions,
      max_iterations: task.max_iterations,
      vision_enabled: task.vision_enabled,
      record_video: task.record_video,
      task: task.task,
    }));
    setSettingsOpen(true);
  }, []);

  const handleSubmit = useCallback(async () => {
    setSubmitError(null);
    if (!form.task.trim()) return setSubmitError("Describe the task the agents should carry out.");
    if (!form.configuration) return setSubmitError("Choose an agent configuration.");
    if (!form.provider || !form.model) return setSubmitError("Choose a provider and model.");

    setSubmitting(true);
    closeStream();
    setSelectedTaskId(null);
    setSelectedTaskDetail(null);
    try {
      const task = await apiClient.createTask({
        configuration: form.configuration,
        provider: form.provider,
        model: form.model,
        task: form.task.trim(),
        base_url: form.base_url.trim() || null,
        num_task_executions: Number(form.num_task_executions) || 1,
        max_iterations: Number(form.max_iterations) || 50,
        vision_enabled: !!form.vision_enabled,
        record_video: !!form.record_video,
      });
      prepend(task);
      setSelectedTaskId(task.id);
      setForm((f) => ({ ...f, task: "" }));
      openStream(task.id, () => {
        refreshTasks();
        apiClient.getTask(task.id).then(setSelectedTaskDetail).catch(() => {});
      });
    } catch (e) {
      setSubmitError(e.message || "Could not start the run.");
    } finally {
      setSubmitting(false);
    }
  }, [apiClient, closeStream, form, prepend, openStream, refreshTasks]);

  const handleStop = useCallback(async () => {
    if (!selectedTaskId) return;
    try {
      await apiClient.cancelTask(selectedTaskId);
      refreshTasks();
    } catch {
      // status simply won't change; the pill reflects reality on next poll
    }
  }, [apiClient, selectedTaskId, refreshTasks]);

  const clearTasks = useCallback(async () => {
    if (!window.confirm("Delete all task history, screenshots, and saved task data?")) return;
    closeStream();
    await apiClient.clearTasks();
    setSelectedTaskId(null);
    setSelectedTaskDetail(null);
    await refreshTasks();
  }, [apiClient, closeStream, refreshTasks]);

  const toggleTaskArchived = useCallback(async (task) => {
    try {
      await apiClient.setTaskArchived(task.id, !task.archived);
      await refreshTasks();
    } catch (error) {
      setSubmitError(error.message || "Could not update the archive state.");
    }
  }, [apiClient, refreshTasks]);

  return (
    <div className={`at-root ${browserStreamingEnabled ? "at-root-streaming" : ""} ${touchEnabled ? "at-root-touch" : ""}`}>
      <Sidebar
        tasks={tasks}
        selectedTaskId={selectedTaskId}
        touchMode={touchEnabled}
        onSelectTask={selectTask}
        onReplayTask={replayTask}
        onLoadTaskSettings={loadTaskSettings}
        onNewRun={startNewRun}
        onClearTasks={clearTasks}
        onToggleArchived={toggleTaskArchived}
        apiBase={touchEnabled ? DEFAULT_API_BASE : apiBase}
        onApiBaseChange={(v) => setApiBase(v || DEFAULT_API_BASE)}
        connError={connError}
      />

      <main className="at-main">
        <TopBar task={selectedTask} onStop={handleStop} touchMode={touchEnabled} />
        <Transcript
          selectedTaskId={selectedTaskId}
          transcript={transcript}
          streaming={streaming}
          task={transcriptTask}
          apiBase={apiBase}
          touchMode={touchEnabled}
        />
        {!touchEnabled && (
          <Composer
            form={form}
            onFormChange={setForm}
            settingsOpen={settingsOpen}
            onToggleSettings={() => setSettingsOpen((s) => !s)}
            configurations={configurations}
            models={models}
            modelsLoaded={modelsLoaded}
            onSubmit={handleSubmit}
            submitting={submitting}
            submitError={submitError}
          />
        )}
      </main>
      {browserStreamingEnabled && (
        <BrowserPreview task={selectedTask} apiBase={apiBase} />
      )}
    </div>
  );
}
