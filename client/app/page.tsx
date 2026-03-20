"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type Task = {
  id: string;
  title: string;
  notes: string;
  completed: boolean;
  category: string;
  priority: "low" | "medium" | "high";
  due_date: string | null;
  due_time: string | null;
  created_at: string;
  updated_at: string;
};

type ApiState = {
  tasks: Task[];
  categories: string[];
  summary: {
    total: number;
    completed: number;
    open: number;
    due_today: number;
  };
};

type ApiPayload = ApiState & {
  task?: Task;
};

type TaskDraft = Pick<Task, "title" | "notes" | "category" | "priority" | "due_date" | "due_time" | "completed">;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:5000/api";

const emptyState: ApiState = {
  tasks: [],
  categories: [],
  summary: { total: 0, completed: 0, open: 0, due_today: 0 },
};

const emptyDraft: TaskDraft = {
  title: "",
  notes: "",
  category: "General",
  priority: "medium",
  due_date: null,
  due_time: null,
  completed: false,
};

const NOTIFIED_TASKS_KEY = "mini-todo-deadline-notified";

function createDraft(task: Task | null): TaskDraft {
  if (!task) {
    return emptyDraft;
  }

  return {
    title: task.title,
    notes: task.notes,
    category: task.category,
    priority: task.priority,
    due_date: task.due_date,
    due_time: task.due_time,
    completed: task.completed,
  };
}

function formatTime(value: string | null) {
  if (!value) {
    return "";
  }

  const [hours, minutes] = value.split(":");
  const due = new Date();
  due.setHours(Number(hours), Number(minutes), 0, 0);
  return due.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

function dueLabel(dateValue: string | null, timeValue: string | null) {
  if (!dateValue && !timeValue) {
    return "No due date";
  }

  if (dateValue && !timeValue) {
    const dueDate = new Date(`${dateValue}T00:00:00`);
    return dueDate.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  }

  if (!dateValue && timeValue) {
    return formatTime(timeValue);
  }

  const dueDate = new Date(`${dateValue}T00:00:00`);
  return `${dueDate.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })} at ${formatTime(timeValue)}`;
}

function relativeDueTone(dateValue: string | null, timeValue: string | null, completed: boolean) {
  if (completed || !dateValue) {
    return "muted";
  }

  const now = new Date();
  const due = new Date(`${dateValue}T00:00:00`);

  if (timeValue) {
    const [hours, minutes] = timeValue.split(":");
    due.setHours(Number(hours), Number(minutes), 0, 0);
  } else {
    due.setHours(23, 59, 59, 999);
  }

  if (due.getTime() < now.getTime()) {
    return "late";
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (due >= today && due < tomorrow) {
    return "today";
  }
  return "upcoming";
}

function getDueAt(task: Task) {
  if (!task.due_date && !task.due_time) {
    return null;
  }

  const baseDate = task.due_date ? new Date(`${task.due_date}T00:00:00`) : new Date();

  if (task.due_time) {
    const [hours, minutes] = task.due_time.split(":");
    baseDate.setHours(Number(hours), Number(minutes), 0, 0);
  } else {
    baseDate.setHours(23, 59, 59, 999);
  }

  return baseDate;
}

function toLocalDateKey(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function deadlineNotificationKey(task: Task) {
  return `${task.id}:${task.due_date ?? ""}:${task.due_time ?? ""}`;
}

function isDueToday(task: Task, now: Date) {
  if (task.completed) {
    return false;
  }

  const dueAt = getDueAt(task);
  if (!dueAt) {
    return false;
  }

  return toLocalDateKey(dueAt) === toLocalDateKey(now) && dueAt.getTime() >= now.getTime();
}

export default function Home() {
  const [data, setData] = useState<ApiState>(emptyState);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "open" | "done" | "due_today">("all");
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [draft, setDraft] = useState<TaskDraft>(emptyDraft);
  const [deadlineMessage, setDeadlineMessage] = useState("");
  const [clockTick, setClockTick] = useState(() => Date.now());
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission | "unsupported">(
    "unsupported"
  );
  const notifiedTaskKeysRef = useRef<Set<string>>(new Set());
  const [createForm, setCreateForm] = useState({
    title: "",
    category: "General",
    priority: "medium" as Task["priority"],
    due_date: "",
    due_time: "",
  });

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });
    const body = (await response.json()) as T & { error?: string };
    if (!response.ok) {
      throw new Error(body.error || "Request failed.");
    }
    return body;
  }

  async function loadTasks() {
    setLoading(true);
    setError("");
    try {
      const next = await request<ApiState>("/tasks");
      setData(next);
      setSelectedId((current) => current || next.tasks[0]?.id || "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load tasks.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void (async () => {
      setLoading(true);
      setError("");
      try {
        const next = await request<ApiState>("/tasks");
        setData(next);
        setSelectedId((current) => current || next.tasks[0]?.id || "");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not load tasks.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("mini-todo-theme", theme);
  }, [theme]);

  useEffect(() => {
    const storedTheme = localStorage.getItem("mini-todo-theme");
    if (storedTheme === "dark" || storedTheme === "light") {
      setTheme(storedTheme);
      document.documentElement.dataset.theme = storedTheme;
    }

    if (typeof window !== "undefined") {
      const storedNotifiedTasks = localStorage.getItem(NOTIFIED_TASKS_KEY);
      if (storedNotifiedTasks) {
        try {
          notifiedTaskKeysRef.current = new Set(JSON.parse(storedNotifiedTasks) as string[]);
        } catch {
          notifiedTaskKeysRef.current = new Set();
        }
      }
    }

    if ("Notification" in window) {
      setNotificationPermission(Notification.permission);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const tickId = window.setInterval(() => setClockTick(Date.now()), 30000);
    return () => window.clearInterval(tickId);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const checkDeadlines = () => {
      const now = Date.now();
      const newlyDueTasks = data.tasks.filter((task) => {
        if (task.completed) {
          return false;
        }

        const dueAt = getDueAt(task);
        if (!dueAt || dueAt.getTime() > now) {
          return false;
        }

        const notificationKey = deadlineNotificationKey(task);
        return !notifiedTaskKeysRef.current.has(notificationKey);
      });

      if (!newlyDueTasks.length) {
        return;
      }

      const nextNotifiedKeys = new Set(notifiedTaskKeysRef.current);
      for (const task of newlyDueTasks) {
        const notificationKey = deadlineNotificationKey(task);
        nextNotifiedKeys.add(notificationKey);

        if ("Notification" in window && Notification.permission === "granted") {
          new Notification("Task deadline reached", {
            body: `${task.title} is due now.`,
          });
        }
      }

      notifiedTaskKeysRef.current = nextNotifiedKeys;
      localStorage.setItem(NOTIFIED_TASKS_KEY, JSON.stringify(Array.from(nextNotifiedKeys)));

      if (newlyDueTasks.length === 1) {
        setDeadlineMessage(`Deadline reached: ${newlyDueTasks[0].title}`);
      } else {
        setDeadlineMessage(`${newlyDueTasks.length} tasks just reached their deadlines.`);
      }
    };

    checkDeadlines();
    const intervalId = window.setInterval(checkDeadlines, 30000);
    return () => window.clearInterval(intervalId);
  }, [data.tasks]);

  const dueTodayCount = useMemo(() => {
    const now = new Date(clockTick);
    return data.tasks.filter((task) => isDueToday(task, now)).length;
  }, [clockTick, data.tasks]);

  const filteredTasks = useMemo(() => {
    const now = new Date(clockTick);

    return data.tasks.filter((task) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "open" && !task.completed) ||
        (filter === "done" && task.completed) ||
        (filter === "due_today" && isDueToday(task, now));
      const matchesCategory = category === "all" || task.category === category;
      const haystack = `${task.title} ${task.notes} ${task.category}`.toLowerCase();
      const matchesQuery = !query || haystack.includes(query.toLowerCase());
      return matchesFilter && matchesCategory && matchesQuery;
    });
  }, [category, clockTick, data.tasks, filter, query]);

  const selectedTask = data.tasks.find((task) => task.id === selectedId) || filteredTasks[0] || null;

  useEffect(() => {
    setDraft(createDraft(selectedTask));
  }, [selectedTask]);

  const isDirty = selectedTask
    ? JSON.stringify(createDraft(selectedTask)) !== JSON.stringify(draft)
    : false;

  async function createTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createForm.title.trim()) {
      setError("Task title is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const next = await request<ApiPayload>("/tasks", {
        method: "POST",
        body: JSON.stringify({
          ...createForm,
          due_date: createForm.due_date || null,
          due_time: createForm.due_time || null,
        }),
      });
      setData(next);
      setCreateForm((current) => ({ ...current, title: "", due_date: "", due_time: "" }));
      setSelectedId(next.task?.id || next.tasks[0]?.id || "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create task.");
    } finally {
      setSaving(false);
    }
  }

  async function patchTask(taskId: string, updates: Partial<TaskDraft>) {
    setSaving(true);
    setError("");
    try {
      const next = await request<ApiPayload>(`/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify(updates),
      });
      setData(next);
      setSelectedId(next.task?.id || taskId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update task.");
    } finally {
      setSaving(false);
    }
  }

  async function saveSelectedTask() {
    if (!selectedTask) {
      return;
    }

    await patchTask(selectedTask.id, draft);
  }

  async function removeTask(taskId: string) {
    setSaving(true);
    setError("");
    try {
      const next = await request<ApiState>(`/tasks/${taskId}`, {
        method: "DELETE",
      });
      setData(next);
      setSelectedId(next.tasks[0]?.id || "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete task.");
    } finally {
      setSaving(false);
    }
  }

  async function clearCompleted() {
    setSaving(true);
    setError("");
    try {
      const next = await request<ApiState>("/tasks", {
        method: "DELETE",
      });
      setData(next);
      setSelectedId(next.tasks[0]?.id || "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not clear completed tasks.");
    } finally {
      setSaving(false);
    }
  }

  async function enableNotifications() {
    if (!("Notification" in window)) {
      setNotificationPermission("unsupported");
      return;
    }

    const permission = await Notification.requestPermission();
    setNotificationPermission(permission);
  }

  return (
    <main className="page-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">developed by: Glenndel</p>
          <h1>PLAN YOUR DAY BY LISTING IT</h1>
          <p className="hero-copy">
            Stay focused. You’ve got this.
          </p>
        </div>
        <div className="topbar-actions">
          <button className="secondary-button" onClick={() => void loadTasks()} disabled={loading || saving}>
            Refresh
          </button>
          <button className="secondary-button" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
            {theme === "light" ? "Dark theme" : "Light theme"}
          </button>
        </div>
      </section>

      <section className="summary-strip">
        <article className="summary-tile">
          <span>{data.summary.total}</span>
          <p>Total task</p>
        </article>
        <article className="summary-tile">
          <span>{data.summary.open}</span>
          <p>Open</p>
        </article>
        <article className="summary-tile">
          <span>{data.summary.completed}</span>
          <p>Closed</p>
        </article>
        <article className="summary-tile">
          <span>{dueTodayCount}</span>
          <p>Due today</p>
        </article>
      </section>

      {deadlineMessage ? (
        <section className="message notice-strip">
          <span>{deadlineMessage}</span>
          <div className="notice-actions">
            {notificationPermission === "default" ? (
              <button className="secondary-button" onClick={() => void enableNotifications()}>
                Enable browser alerts
              </button>
            ) : null}
            <button className="link-button" onClick={() => setDeadlineMessage("")}>
              Dismiss
            </button>
          </div>
        </section>
      ) : null}

      <section className="workspace-grid">
        <aside className="sidebar-panel">
          <form className="panel create-panel" onSubmit={createTask}>
            <div className="panel-heading">
              <div>
                <h2>New task</h2>
                <p>Quick capture with cleaner defaults.</p>
              </div>
              <span className="status-pill">{saving ? "Saving" : "Ready"}</span>
            </div>
            <input
              placeholder="Title"
              value={createForm.title}
              onChange={(event) => setCreateForm((current) => ({ ...current, title: event.target.value }))}
            />
            <div className="split-row">
              <input
                placeholder="Label"
                value={createForm.category}
                onChange={(event) => setCreateForm((current) => ({ ...current, category: event.target.value }))}
              />
              <select
                value={createForm.priority}
                onChange={(event) =>
                  setCreateForm((current) => ({ ...current, priority: event.target.value as Task["priority"] }))
                }
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
              </select>
            </div>
            <input
              type="date"
              value={createForm.due_date}
              onChange={(event) => setCreateForm((current) => ({ ...current, due_date: event.target.value }))}
            />
            <input
              type="time"
              value={createForm.due_time}
              onChange={(event) => setCreateForm((current) => ({ ...current, due_time: event.target.value }))}
            />
            <button type="submit" className="primary-button" disabled={saving}>
              Create task
            </button>
          </form>

          <div className="panel">
            <div className="panel-heading">
              <div>
                <h2>Filters</h2>
                <p>Trim the list to what matters now.</p>
              </div>
              <button
                className="link-button"
                onClick={() => {
                  setFilter("all");
                  setCategory("all");
                  setQuery("");
                }}
              >
                Reset
              </button>
            </div>
            <input placeholder="Search tasks" value={query} onChange={(event) => setQuery(event.target.value)} />
            <div className="tab-row">
              <button className={filter === "all" ? "tab-button active" : "tab-button"} onClick={() => setFilter("all")}>
                All
              </button>
              <button className={filter === "open" ? "tab-button active" : "tab-button"} onClick={() => setFilter("open")}>
                Open
              </button>
              <button className={filter === "done" ? "tab-button active" : "tab-button"} onClick={() => setFilter("done")}>
                Closed
              </button>
              <button
                className={filter === "due_today" ? "tab-button active" : "tab-button"}
                onClick={() => setFilter("due_today")}
              >
                Today
              </button>
            </div>
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="all">All labels</option>
              {data.categories.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <button className="secondary-button" onClick={() => void clearCompleted()} disabled={saving}>
              Clear completed
            </button>
          </div>
        </aside>

        <section className="panel list-panel">
          <div className="panel-heading list-heading">
            <div>
              <h2>Task list</h2>
              <p>{filteredTasks.length} visible items</p>
            </div>
            <span className="status-pill subtle">{loading ? "Syncing" : "Live"}</span>
          </div>

          {loading ? <p className="empty-copy">Loading tasks...</p> : null}
          {!loading && !filteredTasks.length ? <p className="empty-copy">No tasks match the current filter set.</p> : null}

          <div className="task-list">
            {filteredTasks.map((task) => (
              <article
                key={task.id}
                className={`task-row ${selectedTask?.id === task.id ? "selected" : ""}`}
                onClick={() => setSelectedId(task.id)}
              >
                <label className="checkbox-wrap" onClick={(event) => event.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={task.completed}
                    onChange={() => void patchTask(task.id, { completed: !task.completed })}
                  />
                </label>
                <div className="task-main">
                  <div className="task-row-top">
                    <h3>{task.title}</h3>
                    <span className={`priority-pill ${task.priority}`}>{task.priority}</span>
                  </div>
                  <p>{task.notes || "No notes yet."}</p>
                  <div className="meta-row">
                    <span className="meta-badge">{task.category}</span>
                    <span className={`due-badge ${relativeDueTone(task.due_date, task.due_time, task.completed)}`}>
                      {dueLabel(task.due_date, task.due_time)}
                    </span>
                    <span className="meta-muted">
                      Updated{" "}
                      {new Date(task.updated_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="panel details-panel">
          <div className="panel-heading">
            <div>
              <h2>Details</h2>
              <p>{selectedTask ? "Edit locally, then save once." : "Select a task to inspect it here."}</p>
            </div>
            <span className={isDirty ? "status-pill dirty" : "status-pill subtle"}>{isDirty ? "Unsaved" : "Saved"}</span>
          </div>

          {selectedTask ? (
            <div className="details-form">
              <input value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} />
              <textarea
                rows={7}
                value={draft.notes}
                placeholder="Add notes"
                onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
              />
              <div className="split-row">
                <input
                  value={draft.category}
                  onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))}
                />
                <select
                  value={draft.priority}
                  onChange={(event) =>
                    setDraft((current) => ({ ...current, priority: event.target.value as Task["priority"] }))
                  }
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
              <input
                type="date"
                value={draft.due_date ?? ""}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, due_date: event.target.value || null }))
                }
              />
              <input
                type="time"
                value={draft.due_time ?? ""}
                onChange={(event) =>
                  setDraft((current) => ({ ...current, due_time: event.target.value || null }))
                }
              />
              <label className="checkline">
                <input
                  type="checkbox"
                  checked={draft.completed}
                  onChange={(event) => setDraft((current) => ({ ...current, completed: event.target.checked }))}
                />
                Mark task as completed
              </label>
              <div className="details-actions">
                <button className="primary-button" onClick={() => void saveSelectedTask()} disabled={!isDirty || saving}>
                  Save changes
                </button>
                <button className="secondary-button" onClick={() => setDraft(createDraft(selectedTask))} disabled={!isDirty || saving}>
                  Reset draft
                </button>
                <button className="danger-button" onClick={() => void removeTask(selectedTask.id)} disabled={saving}>
                  Delete
                </button>
              </div>
            </div>
          ) : (
            <p className="empty-copy">Pick a task from the list to edit it here.</p>
          )}

          {error ? <p className="message error">{error}</p> : null}
        </aside>
      </section>
    </main>
  );
}
