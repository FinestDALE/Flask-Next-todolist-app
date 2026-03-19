"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

type Task = {
  id: string;
  title: string;
  notes: string;
  completed: boolean;
  category: string;
  priority: "low" | "medium" | "high";
  due_date: string;
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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:5000/api";

const emptyState: ApiState = {
  tasks: [],
  categories: [],
  summary: { total: 0, completed: 0, open: 0, due_today: 0 },
};

export default function Home() {
  const [data, setData] = useState<ApiState>(emptyState);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "open" | "done">("all");
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [createForm, setCreateForm] = useState({
    title: "",
    category: "General",
    priority: "medium" as Task["priority"],
    due_date: "",
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
    const storedTheme = localStorage.getItem("mini-todo-theme");
    if (storedTheme === "dark" || storedTheme === "light") {
      setTheme(storedTheme);
      document.documentElement.dataset.theme = storedTheme;
    }
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

  const filteredTasks = useMemo(() => {
    return data.tasks.filter((task) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "open" && !task.completed) ||
        (filter === "done" && task.completed);
      const matchesCategory = category === "all" || task.category === category;
      const haystack = `${task.title} ${task.notes} ${task.category}`.toLowerCase();
      const matchesQuery = !query || haystack.includes(query.toLowerCase());
      return matchesFilter && matchesCategory && matchesQuery;
    });
  }, [category, data.tasks, filter, query]);

  const selectedTask = data.tasks.find((task) => task.id === selectedId) || filteredTasks[0] || null;

  async function createTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createForm.title.trim()) {
      setError("Task title is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const next = await request<ApiState>("/tasks", {
        method: "POST",
        body: JSON.stringify(createForm),
      });
      setData(next);
      setCreateForm((current) => ({ ...current, title: "", due_date: "" }));
      setSelectedId(next.tasks[0]?.id || "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create task.");
    } finally {
      setSaving(false);
    }
  }

  async function patchTask(taskId: string, updates: Partial<Task>) {
    setSaving(true);
    setError("");
    try {
      const next = await request<ApiState>(`/tasks/${taskId}`, {
        method: "PATCH",
        body: JSON.stringify(updates),
      });
      setData(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not update task.");
    } finally {
      setSaving(false);
    }
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

  return (
    <main className="page-shell">
      <section className="hero-card">
        <div>
          <p className="eyebrow">Small Todo App</p>
          <h1>Simple planning with a cleaner rhythm.</h1>
          <p className="hero-copy">
            Add tasks fast, keep the list tidy, and manage your day with a light modern interface.
          </p>
        </div>
        <div className="hero-actions">
          <button className="ghost-button" onClick={() => void loadTasks()} disabled={loading || saving}>
            Refresh
          </button>
          <button className="ghost-button" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
            {theme === "light" ? "Dark mode" : "Light mode"}
          </button>
        </div>
      </section>

      <section className="dashboard-grid">
        <aside className="sidebar-card">
          <div className="stat-grid">
            <article className="stat-tile coral">
              <span>{data.summary.total}</span>
              <p>Total</p>
            </article>
            <article className="stat-tile teal">
              <span>{data.summary.open}</span>
              <p>Open</p>
            </article>
            <article className="stat-tile gold">
              <span>{data.summary.due_today}</span>
              <p>Due today</p>
            </article>
          </div>

          <form className="create-card" onSubmit={createTask}>
            <div className="section-title">
              <h2>Quick Add</h2>
              <span>{saving ? "Saving..." : "Ready"}</span>
            </div>
            <input
              placeholder="What needs to be done?"
              value={createForm.title}
              onChange={(event) => setCreateForm((current) => ({ ...current, title: event.target.value }))}
            />
            <div className="compact-grid">
              <input
                placeholder="Category"
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
            <button type="submit">Add Task</button>
          </form>

          <div className="filter-card">
            <div className="section-title">
              <h2>Filters</h2>
              <button className="text-button" onClick={() => { setFilter("all"); setCategory("all"); setQuery(""); }}>
                Reset
              </button>
            </div>
            <input placeholder="Search tasks" value={query} onChange={(event) => setQuery(event.target.value)} />
            <div className="chip-row">
              <button className={filter === "all" ? "active" : ""} onClick={() => setFilter("all")}>All</button>
              <button className={filter === "open" ? "active" : ""} onClick={() => setFilter("open")}>Open</button>
              <button className={filter === "done" ? "active" : ""} onClick={() => setFilter("done")}>Done</button>
            </div>
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="all">All categories</option>
              {data.categories.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <button className="ghost-button" onClick={() => void clearCompleted()}>
              Clear Completed
            </button>
          </div>
        </aside>

        <section className="list-card">
          <div className="section-title">
            <h2>Tasks</h2>
            <span>{filteredTasks.length} visible</span>
          </div>

          {loading ? <p className="empty-copy">Loading tasks...</p> : null}
          {!loading && !filteredTasks.length ? <p className="empty-copy">No tasks match your filters yet.</p> : null}

          <div className="task-list">
            {filteredTasks.map((task) => (
              <article
                key={task.id}
                className={`task-row-card ${selectedTask?.id === task.id ? "selected" : ""}`}
                onClick={() => setSelectedId(task.id)}
              >
                <label className="checkbox-wrap" onClick={(event) => event.stopPropagation()}>
                  <input
                    type="checkbox"
                    checked={task.completed}
                    onChange={() => void patchTask(task.id, { completed: !task.completed })}
                  />
                </label>
                <div className="task-copy">
                  <h3>{task.title}</h3>
                  <p>{task.notes || "No notes yet."}</p>
                  <div className="meta-row">
                    <span className={`priority-badge ${task.priority}`}>{task.priority}</span>
                    <span>{task.category}</span>
                    <span>{task.due_date || "No due date"}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="details-card">
          <div className="section-title">
            <h2>Details</h2>
            <span>{selectedTask ? "Edit task" : "Select one"}</span>
          </div>

          {selectedTask ? (
            <div className="details-form">
              <input
                value={selectedTask.title}
                onChange={(event) => void patchTask(selectedTask.id, { title: event.target.value })}
              />
              <textarea
                rows={6}
                value={selectedTask.notes}
                placeholder="Add notes"
                onChange={(event) => void patchTask(selectedTask.id, { notes: event.target.value })}
              />
              <div className="compact-grid">
                <input
                  value={selectedTask.category}
                  onChange={(event) => void patchTask(selectedTask.id, { category: event.target.value })}
                />
                <select
                  value={selectedTask.priority}
                  onChange={(event) =>
                    void patchTask(selectedTask.id, { priority: event.target.value as Task["priority"] })
                  }
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
              <input
                type="date"
                value={selectedTask.due_date}
                onChange={(event) => void patchTask(selectedTask.id, { due_date: event.target.value })}
              />
              <div className="detail-actions">
                <button onClick={() => void patchTask(selectedTask.id, { completed: !selectedTask.completed })}>
                  {selectedTask.completed ? "Mark Open" : "Mark Done"}
                </button>
                <button className="danger-button" onClick={() => void removeTask(selectedTask.id)}>
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
