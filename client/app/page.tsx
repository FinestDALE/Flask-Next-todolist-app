"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type Task = {
  id: string;
  title: string;
  notes: string;
  completed: boolean;
  category: string;
  priority: "low" | "medium" | "high";
  dueDate: string | null;
  dueTime: string | null;
  createdAt: string;
  updatedAt: string;
};

type User = {
  id: string;
  name: string;
  email: string;
  createdAt: string;
};

type ApiState = {
  tasks: Task[];
  categories: string[];
  summary: {
    total: number;
    completed: number;
    open: number;
    dueToday: number;
  };
};

type ApiPayload = ApiState & {
  task?: Task;
};

type SessionPayload = {
  user: User | null;
  expiresAt?: string;
};

type BasicApiMessage = {
  ok: boolean;
  message?: string;
};

type TaskDraft = Pick<Task, "title" | "notes" | "category" | "priority" | "dueDate" | "dueTime" | "completed">;

type AuthMode = "login" | "register";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:5000/api";

const emptyState: ApiState = {
  tasks: [],
  categories: [],
  summary: { total: 0, completed: 0, open: 0, dueToday: 0 },
};

const emptyDraft: TaskDraft = {
  title: "",
  notes: "",
  category: "General",
  priority: "medium",
  dueDate: null,
  dueTime: null,
  completed: false,
};

function createDraft(task: Task | null): TaskDraft {
  if (!task) {
    return emptyDraft;
  }

  return {
    title: task.title,
    notes: task.notes,
    category: task.category,
    priority: task.priority,
    dueDate: task.dueDate,
    dueTime: task.dueTime,
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

function toLocalDateKey(value: Date) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getDueAt(task: Task) {
  if (!task.dueDate && !task.dueTime) {
    return null;
  }

  const baseDate = task.dueDate ? new Date(`${task.dueDate}T00:00:00`) : new Date();
  if (task.dueTime) {
    const [hours, minutes] = task.dueTime.split(":");
    baseDate.setHours(Number(hours), Number(minutes), 0, 0);
  } else {
    baseDate.setHours(23, 59, 59, 999);
  }
  return baseDate;
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
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [booting, setBooting] = useState(true);
  const [loadingTasks, setLoadingTasks] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [authError, setAuthError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [isSecurityOpen, setIsSecurityOpen] = useState(false);
  const [filter, setFilter] = useState<"all" | "open" | "done" | "dueToday">("all");
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [clockTick, setClockTick] = useState(() => Date.now());
  const [draft, setDraft] = useState<TaskDraft>(emptyDraft);
  const [createForm, setCreateForm] = useState({
    title: "",
    category: "General",
    priority: "medium" as Task["priority"],
    dueDate: "",
    dueTime: "",
  });
  const [loginForm, setLoginForm] = useState({
    email: "",
    password: "",
  });
  const [registerForm, setRegisterForm] = useState({
    name: "",
    email: "",
    password: "",
  });
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: "",
    newPassword: "",
    confirmPassword: "",
  });
  const noticeRef = useRef<HTMLDivElement | null>(null);

  function isUnauthorizedError(value: unknown) {
    return typeof value === "object" && value !== null && "status" in value && Number(value.status) === 401;
  }

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });

    const contentType = response.headers.get("content-type") || "";
    const rawBody = await response.text();
    const body = contentType.includes("application/json")
      ? (JSON.parse(rawBody) as T & { error?: string; user?: User | null })
      : null;

    if (!response.ok) {
      const fallbackMessage = rawBody.trim().startsWith("<")
        ? "The API returned an HTML error page. Make sure the Flask server is running and restart both apps."
        : rawBody.trim() || "Request failed.";
      throw Object.assign(new Error(body?.error || fallbackMessage), { status: response.status, body: body ?? rawBody });
    }

    if (!body) {
      throw Object.assign(
        new Error("The API did not return JSON. Make sure the request is hitting the Flask server."),
        { status: response.status, body: rawBody }
      );
    }

    return body;
  }

  async function loadTasks() {
    setLoadingTasks(true);
    setError("");
    try {
      const next = await request<ApiState>("/tasks");
      setData(next);
      setSelectedId((current) => current || next.tasks[0]?.id || "");
    } catch (caught) {
      if (isUnauthorizedError(caught)) {
        setUser(null);
        setAuthError("Your session expired. Please sign in again.");
        resetBoardState();
        return;
      }
      setError(caught instanceof Error ? caught.message : "Could not load tasks.");
    } finally {
      setLoadingTasks(false);
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        let currentUser: User | null = null;
        try {
          const session = await request<SessionPayload>("/auth/session");
          currentUser = session.user;
          setUser(session.user);
        } catch (caught) {
          const status = typeof caught === "object" && caught && "status" in caught ? Number(caught.status) : 0;
          if (status === 401) {
            setUser(null);
          } else {
            throw caught;
          }
        }

        if (currentUser) {
          setLoadingTasks(true);
          setError("");
          try {
            const next = await request<ApiState>("/tasks");
            setData(next);
            setSelectedId(next.tasks[0]?.id || "");
          } catch (caught) {
            setError(caught instanceof Error ? caught.message : "Could not load tasks.");
          } finally {
            setLoadingTasks(false);
          }
        }
      } catch (caught) {
        setAuthError(caught instanceof Error ? caught.message : "Could not connect to the server.");
      } finally {
        setBooting(false);
      }
    })();
  }, []);

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("mini-todo-theme");
    if (storedTheme === "dark" || storedTheme === "light") {
      setTheme(storedTheme);
      document.documentElement.dataset.theme = storedTheme;
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("mini-todo-theme", theme);
  }, [theme]);

  useEffect(() => {
    const tickId = window.setInterval(() => setClockTick(Date.now()), 30000);
    return () => window.clearInterval(tickId);
  }, []);

  useEffect(() => {
    if (error || authError) {
      noticeRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [authError, error]);

  useEffect(() => {
    if (!isSecurityOpen) {
      return undefined;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsSecurityOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isSecurityOpen]);

  useEffect(() => {
    if (!isSecurityOpen) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isSecurityOpen]);

  const filteredTasks = useMemo(() => {
    const now = new Date(clockTick);
    return data.tasks.filter((task) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "open" && !task.completed) ||
        (filter === "done" && task.completed) ||
        (filter === "dueToday" && isDueToday(task, now));
      const matchesCategory = category === "all" || task.category === category;
      const haystack = `${task.title} ${task.notes} ${task.category}`.toLowerCase();
      const matchesQuery = !query || haystack.includes(query.toLowerCase());
      return matchesFilter && matchesCategory && matchesQuery;
    });
  }, [category, clockTick, data.tasks, filter, query]);

  const selectedTask = data.tasks.find((task) => task.id === selectedId) || filteredTasks[0] || null;
  const dueTodayCount = useMemo(() => {
    const now = new Date(clockTick);
    return data.tasks.filter((task) => isDueToday(task, now)).length;
  }, [clockTick, data.tasks]);

  const isDirty = selectedTask ? JSON.stringify(createDraft(selectedTask)) !== JSON.stringify(draft) : false;

  useEffect(() => {
    setDraft(createDraft(selectedTask));
  }, [selectedTask]);

  function resetBoardState() {
    setData(emptyState);
    setSelectedId("");
    setDraft(emptyDraft);
    setFilter("all");
    setCategory("all");
    setQuery("");
    setError("");
    setPasswordError("");
    setPasswordMessage("");
    setIsSecurityOpen(false);
    setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
  }

  function openSecurityDialog() {
    setPasswordError("");
    setPasswordMessage("");
    setIsSecurityOpen(true);
  }

  function closeSecurityDialog() {
    if (passwordBusy) {
      return;
    }
    setIsSecurityOpen(false);
    setPasswordError("");
    setPasswordMessage("");
    setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
  }

  function validateDeadlineInput(dateValue: string | null, timeValue: string | null) {
    if (!dateValue && !timeValue) {
      return "";
    }

    if (!dateValue || !timeValue) {
      return "Please choose both a due date and due time.";
    }

    const now = new Date();
    const today = new Date(now);
    today.setHours(0, 0, 0, 0);
    const dueDate = new Date(`${dateValue}T00:00:00`);

    if (Number.isNaN(dueDate.getTime())) {
      return "Please choose a valid due date and time.";
    }

    if (dueDate < today) {
      return "Due date cannot be earlier than today.";
    }

    if (dueDate.getTime() === today.getTime()) {
      const [hours, minutes] = timeValue.split(":");
      const dueMinutes = Number(hours) * 60 + Number(minutes);
      const nowMinutes = now.getHours() * 60 + now.getMinutes();
      if (dueMinutes < nowMinutes) {
        return "Due time cannot be earlier than the current time.";
      }
    }

    return "";
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError("");
    try {
      const session = await request<SessionPayload>("/auth/register", {
        method: "POST",
        body: JSON.stringify(registerForm),
      });
      setUser(session.user);
      setRegisterForm({ name: "", email: "", password: "" });
      await loadTasks();
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : "Could not create your account.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthBusy(true);
    setAuthError("");
    try {
      const session = await request<SessionPayload>("/auth/login", {
        method: "POST",
        body: JSON.stringify(loginForm),
      });
      setUser(session.user);
      setLoginForm((current) => ({ ...current, password: "" }));
      await loadTasks();
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : "Could not sign you in.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function handleLogout() {
    setAuthBusy(true);
    setAuthError("");
    try {
      await request<BasicApiMessage>("/auth/logout", { method: "POST" });
      setUser(null);
      resetBoardState();
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : "Could not sign you out.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function handlePasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordBusy(true);
    setPasswordError("");
    setPasswordMessage("");
    try {
      const response = await request<BasicApiMessage>("/auth/change-password", {
        method: "POST",
        body: JSON.stringify(passwordForm),
      });
      setPasswordForm({ currentPassword: "", newPassword: "", confirmPassword: "" });
      setPasswordMessage(response.message || "Password updated successfully.");
      window.setTimeout(() => {
        setIsSecurityOpen(false);
        setPasswordMessage("");
      }, 900);
    } catch (caught) {
      if (isUnauthorizedError(caught)) {
        setUser(null);
        setAuthError("Your session expired. Please sign in again.");
        resetBoardState();
        return;
      }
      setPasswordError(caught instanceof Error ? caught.message : "Could not change your password.");
    } finally {
      setPasswordBusy(false);
    }
  }

  async function createTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!createForm.title.trim()) {
      setError("Task title is required.");
      return;
    }

    const deadlineError = validateDeadlineInput(createForm.dueDate || null, createForm.dueTime || null);
    if (deadlineError) {
      setError(deadlineError);
      return;
    }

    setSaving(true);
    setError("");
    try {
      const next = await request<ApiPayload>("/tasks", {
        method: "POST",
        body: JSON.stringify({
          ...createForm,
          dueDate: createForm.dueDate || null,
          dueTime: createForm.dueTime || null,
        }),
      });
      setData(next);
      setCreateForm((current) => ({ ...current, title: "", dueDate: "", dueTime: "" }));
      setSelectedId(next.task?.id || next.tasks[0]?.id || "");
    } catch (caught) {
      if (isUnauthorizedError(caught)) {
        setUser(null);
        setAuthError("Your session expired. Please sign in again.");
        resetBoardState();
        return;
      }
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
      if (isUnauthorizedError(caught)) {
        setUser(null);
        setAuthError("Your session expired. Please sign in again.");
        resetBoardState();
        return;
      }
      setError(caught instanceof Error ? caught.message : "Could not update task.");
    } finally {
      setSaving(false);
    }
  }

  async function saveSelectedTask() {
    if (!selectedTask) {
      return;
    }

    const deadlineError = validateDeadlineInput(draft.dueDate, draft.dueTime);
    if (deadlineError) {
      setError(deadlineError);
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
      if (isUnauthorizedError(caught)) {
        setUser(null);
        setAuthError("Your session expired. Please sign in again.");
        resetBoardState();
        return;
      }
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
      if (isUnauthorizedError(caught)) {
        setUser(null);
        setAuthError("Your session expired. Please sign in again.");
        resetBoardState();
        return;
      }
      setError(caught instanceof Error ? caught.message : "Could not clear completed tasks.");
    } finally {
      setSaving(false);
    }
  }

  if (booting) {
    return (
      <main className="launch-shell">
        <section className="launch-card">
          <p className="eyebrow">Mongo-backed productivity workspace</p>
          <h1>Preparing your planning space</h1>
          <p className="hero-copy">Checking the current session and waking up the API.</p>
        </section>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="auth-shell">
        <section className="auth-hero">
          <p className="eyebrow">Developed by:Glenndel</p>
          <h1>Plan faster with a calmer workspace.</h1>
          <p className="hero-copy">
            Register once, sign in securely, and keep every task attached to your own account.
          </p>
          <div className="hero-preview">
            <div className="hero-preview__header">
              <span>Your day at a glance</span>
              <strong>Personal board</strong>
            </div>
            <div className="hero-preview__grid">
              <article>
                <strong>Capture</strong>
                <p>Quickly add work with priority and due date.</p>
              </article>
              <article>
                <strong>Focus</strong>
                <p>Filter by open work, done tasks, or due today.</p>
              </article>
              <article>
                <strong>Own it</strong>
                <p>Your tasks stay tied to your account in database.</p>
              </article>
            </div>
          </div>
          <div className="hero-stats">
            <article>
              <strong>Secure</strong>
              <span>Hashed passwords and server sessions.</span>
            </article>
            <article>
              <strong>Focused</strong>
              <span>Per-user task boards with cleaner defaults.</span>
            </article>
            <article>
              <strong>Presentable</strong>
              <span>A softer, dashboard-style UI that feels ready to use.</span>
            </article>
          </div>
        </section>

        <section className="auth-card">
          <div className="auth-card__header">
            <div>
              <p className="eyebrow">Welcome back</p>
              <h2>{authMode === "login" ? "Sign in to continue" : "Create your account"}</h2>
              <p className="auth-subcopy">
                {authMode === "login"
                  ? "Pick up where you left off in your private planning board."
                  : "Create a secure account and get a starter board immediately."}
              </p>
            </div>
            <button className="theme-toggle" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
              {theme === "light" ? "Dark" : "Light"}
            </button>
          </div>

          <div className="auth-tabs">
            <button
              className={authMode === "login" ? "tab-button active" : "tab-button"}
              onClick={() => setAuthMode("login")}
              type="button"
            >
              Login
            </button>
            <button
              className={authMode === "register" ? "tab-button active" : "tab-button"}
              onClick={() => setAuthMode("register")}
              type="button"
            >
              Register
            </button>
          </div>

          <div ref={noticeRef}>{authError ? <p className="message error">{authError}</p> : null}</div>

          {authMode === "login" ? (
            <form className="auth-form" onSubmit={handleLogin}>
              <label>
                <span>Email</span>
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={loginForm.email}
                  onChange={(event) => setLoginForm((current) => ({ ...current, email: event.target.value }))}
                />
              </label>
              <label>
                <span>Password</span>
                <input
                  type="password"
                  placeholder="Enter your password"
                  value={loginForm.password}
                  onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
                />
              </label>
              <button className="primary-button" type="submit" disabled={authBusy}>
                {authBusy ? "Signing in..." : "Sign in"}
              </button>
              <p className="auth-footnote">Use the account you created on this device. Sessions stay active for 14 days.</p>
            </form>
          ) : (
            <form className="auth-form" onSubmit={handleRegister}>
              <label>
                <span>Full name</span>
                <input
                  placeholder="Glenndel"
                  value={registerForm.name}
                  onChange={(event) => setRegisterForm((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label>
                <span>Email</span>
                <input
                  type="email"
                  placeholder="you@example.com"
                  value={registerForm.email}
                  onChange={(event) => setRegisterForm((current) => ({ ...current, email: event.target.value }))}
                />
              </label>
              <label>
                <span>Password</span>
                <input
                  type="password"
                  placeholder="Minimum 8 characters"
                  value={registerForm.password}
                  onChange={(event) => setRegisterForm((current) => ({ ...current, password: event.target.value }))}
                />
              </label>
              <button className="primary-button" type="submit" disabled={authBusy}>
                {authBusy ? "Creating account..." : "Create account"}
              </button>
              <p className="auth-footnote">Passwords are stored as hashes, not plain text, before being saved to MongoDB.</p>
            </form>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <section className="topbar">
        <div>
          <p className="eyebrow">Logged in as {user.email}</p>
          <h1>{user.name.split(" ")[0]}&apos;s task dashboard</h1>
          <p className="hero-copy">Keep momentum high with one clean board for capture, triage, and delivery.</p>
        </div>
        <div className="topbar-actions">
          <button className="secondary-button" onClick={() => void loadTasks()} disabled={loadingTasks || saving}>
            Refresh
          </button>
          <button className="secondary-button" onClick={openSecurityDialog} disabled={authBusy}>
            Account security
          </button>
          <button className="secondary-button" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
            {theme === "light" ? "Dark theme" : "Light theme"}
          </button>
          <button className="secondary-button" onClick={() => void handleLogout()} disabled={authBusy}>
            Sign out
          </button>
        </div>
      </section>

      <section className="summary-strip">
        <article className="summary-tile accent">
          <p className="summary-label">Total</p>
          <span>{data.summary.total}</span>
          <p>Total tasks</p>
        </article>
        <article className="summary-tile">
          <p className="summary-label">In Focus</p>
          <span>{data.summary.open}</span>
          <p>Open</p>
        </article>
        <article className="summary-tile">
          <p className="summary-label">Progress</p>
          <span>{data.summary.completed}</span>
          <p>Completed</p>
        </article>
        <article className="summary-tile">
          <p className="summary-label">Today</p>
          <span>{dueTodayCount}</span>
          <p>Due today</p>
        </article>
      </section>

      <div ref={noticeRef}>{error ? <p className="message error">{error}</p> : null}</div>

      <section className="workspace-grid">
        <aside className="sidebar-panel workspace-sidebar">
          <form className="panel create-panel" onSubmit={createTask}>
            <div className="panel-heading">
              <div>
                <h2>Quick capture</h2>
                <p>Create new work without leaving the board.</p>
              </div>
              <span className="status-pill">{saving ? "Saving" : "Ready"}</span>
            </div>
            <input
              placeholder="What needs to get done?"
              value={createForm.title}
              onChange={(event) => setCreateForm((current) => ({ ...current, title: event.target.value }))}
            />
            <div className="split-row">
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
            <div className="split-row">
              <input
                type="date"
                value={createForm.dueDate}
                onChange={(event) => setCreateForm((current) => ({ ...current, dueDate: event.target.value }))}
              />
              <input
                type="time"
                value={createForm.dueTime}
                onChange={(event) => setCreateForm((current) => ({ ...current, dueTime: event.target.value }))}
              />
            </div>
            <button type="submit" className="primary-button" disabled={saving}>
              Create task
            </button>
          </form>

          <div className="panel">
            <div className="panel-heading">
              <div>
                <h2>Filters</h2>
                <p>Focus the board on what matters right now.</p>
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
                Done
              </button>
              <button
                className={filter === "dueToday" ? "tab-button active" : "tab-button"}
                onClick={() => setFilter("dueToday")}
              >
                Today
              </button>
            </div>
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="all">All categories</option>
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

        <section className="panel list-panel workspace-main">
          <div className="panel-heading list-heading">
            <div>
              <h2>Active board</h2>
              <p>{filteredTasks.length} visible items</p>
            </div>
            <span className="status-pill subtle">{loadingTasks ? "Syncing" : "Live"}</span>
          </div>

          {loadingTasks ? <p className="empty-copy">Loading tasks...</p> : null}
          {!loadingTasks && !filteredTasks.length ? <p className="empty-copy">No tasks match the current filters.</p> : null}

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
                    <span className={`due-badge ${relativeDueTone(task.dueDate, task.dueTime, task.completed)}`}>
                      {dueLabel(task.dueDate, task.dueTime)}
                    </span>
                    <span className="meta-muted">
                      Updated{" "}
                      {new Date(task.updatedAt).toLocaleDateString(undefined, {
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

        <aside className="details-panel workspace-details">
          <section className="panel details-panel__editor">
            <div className="panel-heading">
              <div>
                <h2>Task details</h2>
                <p>{selectedTask ? "Edit everything here, then save once." : "Pick a task to inspect and update it."}</p>
              </div>
              <span className={isDirty ? "status-pill dirty" : "status-pill subtle"}>{isDirty ? "Unsaved" : "Saved"}</span>
            </div>

            {selectedTask ? (
              <div className="details-form">
                <input value={draft.title} onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))} />
                <textarea
                  rows={8}
                  value={draft.notes}
                  placeholder="Add notes, context, or acceptance criteria"
                  onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
                />
                <div className="split-row">
                  <input
                    value={draft.category}
                    onChange={(event) => setDraft((current) => ({ ...current, category: event.target.value }))}
                  />
                  <select
                    value={draft.priority}
                    onChange={(event) => setDraft((current) => ({ ...current, priority: event.target.value as Task["priority"] }))}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                  </select>
                </div>
                <div className="split-row">
                  <input
                    type="date"
                    value={draft.dueDate ?? ""}
                    onChange={(event) => setDraft((current) => ({ ...current, dueDate: event.target.value || null }))}
                  />
                  <input
                    type="time"
                    value={draft.dueTime ?? ""}
                    onChange={(event) => setDraft((current) => ({ ...current, dueTime: event.target.value || null }))}
                  />
                </div>
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
                    Reset
                  </button>
                  <button className="danger-button" onClick={() => void removeTask(selectedTask.id)} disabled={saving}>
                    Delete
                  </button>
                </div>
              </div>
            ) : (
              <p className="empty-copy">Pick a task from the list to edit it here.</p>
            )}
          </section>

          <section className="panel details-panel__summary">
            <div className="panel-heading compact">
              <div>
                <h2>Board snapshot</h2>
                <p>A quick status check for your current workspace.</p>
              </div>
            </div>
            <div className="mini-stats">
              <article className="mini-stats__tile">
                <strong>{data.summary.open}</strong>
                <span>Open items</span>
              </article>
              <article className="mini-stats__tile">
                <strong>{data.summary.completed}</strong>
                <span>Completed</span>
              </article>
              <article className="mini-stats__tile">
                <strong>{dueTodayCount}</strong>
                <span>Due today</span>
              </article>
            </div>
          </section>
        </aside>
      </section>

      {isSecurityOpen ? (
        <div className="dialog-backdrop" onClick={closeSecurityDialog}>
          <section
            className="dialog-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="account-security-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="panel-heading compact dialog-card__header">
              <div>
                <p className="eyebrow">Account</p>
                <h2 id="account-security-title">Change password</h2>
                <p>Keep your account secure without interrupting your planning flow.</p>
              </div>
              <button className="theme-toggle dialog-close" onClick={closeSecurityDialog} type="button" disabled={passwordBusy}>
                Close
              </button>
            </div>

            {passwordError ? <p className="message error inline-message">{passwordError}</p> : null}
            {passwordMessage ? <p className="message success inline-message">{passwordMessage}</p> : null}

            <form className="details-form account-form" onSubmit={handlePasswordChange}>
              <label>
                <span>Current password</span>
                <input
                  type="password"
                  value={passwordForm.currentPassword}
                  onChange={(event) =>
                    setPasswordForm((current) => ({ ...current, currentPassword: event.target.value }))
                  }
                />
              </label>
              <label>
                <span>New password</span>
                <input
                  type="password"
                  placeholder="Minimum 8 characters"
                  value={passwordForm.newPassword}
                  onChange={(event) => setPasswordForm((current) => ({ ...current, newPassword: event.target.value }))}
                />
              </label>
              <label>
                <span>Confirm new password</span>
                <input
                  type="password"
                  value={passwordForm.confirmPassword}
                  onChange={(event) =>
                    setPasswordForm((current) => ({ ...current, confirmPassword: event.target.value }))
                  }
                />
              </label>
              <div className="details-actions dialog-actions">
                <button className="secondary-button" type="button" onClick={closeSecurityDialog} disabled={passwordBusy}>
                  Cancel
                </button>
                <button className="primary-button" type="submit" disabled={passwordBusy}>
                  {passwordBusy ? "Updating password..." : "Change password"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </main>
  );
}
