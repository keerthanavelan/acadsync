"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  CalendarDays,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Clock3,
  ExternalLink,
  GraduationCap,
  LayoutDashboard,
  Link2,
  Loader2,
  LogOut,
  Mail,
  Menu,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
  SlidersHorizontal,
  MapPin,
  AlertCircle,
  Pencil,
  Inbox,
} from "lucide-react";

type Event = {
  id: string;
  title: string;
  start: string | null;
  end: string | null;
  category: string;
  venue: string;
  description: string;
  confidence: number;
  warnings: string[];
  status: string;
  source: string;
  source_url: string;
  timezone: string;
  all_day: boolean;
  calendar_synced?: boolean;
};
type Profile = {
  authenticated: boolean;
  provider?: "google" | "outlook";
  demo?: boolean;
  name?: string;
  email?: string;
  connected?: boolean;
  last_sync?: string;
  timezone?: string;
  demo_enabled?: boolean;
};
type Notice = {
  id: string;
  title: string;
  received_at: string;
  source: string;
  result: string;
};
const categories = [
  "Assignment",
  "Exam",
  "Quiz",
  "Submission",
  "Seminar",
  "Deadline",
];
const nav = [
  ["dashboard", "Overview", LayoutDashboard],
  ["calendar", "Academic calendar", CalendarDays],
  ["review", "Event review", CheckCheck],
  ["sources", "Connected sources", Link2],
  ["settings", "Settings", Settings],
] as const;
async function api(path: string, method = "GET", body?: unknown) {
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "Cannot reach the server. Check that the backend is running and try again.",
    );
  }
  const data = await response
    .json()
    .catch(() => ({ detail: "The service is unavailable. Please try again." }));
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Please check the event details and try again.",
    );
  return data;
}
const fmt = (
  date: string | null,
  opts: Intl.DateTimeFormatOptions = {},
  zone?: string,
) =>
  date
    ? new Date(date).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        ...opts,
        ...(zone ? { timeZone: zone } : {}),
      })
    : "Date needs review";
const time = (e: Event) =>
  e.all_day
    ? "All day"
    : e.start
      ? new Date(e.start).toLocaleTimeString("en-US", {
          hour: "numeric",
          minute: "2-digit",
          timeZone: e.timezone,
        })
      : "Time to confirm";
const color = (category: string) => category.toLowerCase();

export default function AcadSync({
  initial = "landing",
}: {
  initial?: string;
}) {
  const [profile, setProfile] = useState<Profile | null>(null),
    [events, setEvents] = useState<Event[]>([]),
    [notices, setNotices] = useState<Notice[]>([]);
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [toast, setToast] = useState(""),
    [mobile, setMobile] = useState(false);
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("All"),
    [editing, setEditing] = useState<Event | null>(null),
    [selected, setSelected] = useState<Event | null>(null);
  const [month, setMonth] = useState(new Date()),
    [view, setView] = useState("Month"),
    [tz, setTz] = useState("Asia/Kolkata");
  const load = useCallback(async () => {
    try {
      const p = await api("/me");
      setProfile(p);
      setTz(p.timezone || "Asia/Kolkata");
      if (p.authenticated) {
        const [e, n] = await Promise.all([api("/events"), api("/notices")]);
        setEvents(e);
        setNotices(n);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    const failure = params.get("auth");
    if (failure) {
      const google = params.get("provider") === "google";
      const reasons: Record<string, string> = {
        denied:
          "Sign-in was cancelled. Try again and allow both Gmail read access and Google Calendar access.",
        permissions:
          "Google did not grant all required permissions. Reconnect and select both Gmail and Calendar permissions.",
        expired:
          "Your sign-in attempt expired. Start Connect Gmail again in this browser.",
        invalid:
          "This sign-in attempt is invalid or already used. Start Connect Gmail again.",
        exchange:
          "Google sign-in failed. Check the client ID, secret and exact redirect URI in backend/.env, and add your Gmail account as a Google OAuth test user.",
      };
      setError(
        google
          ? reasons[failure] || "Google sign-in failed. Please try again."
          : "Microsoft sign-in was not completed. Your institution may require administrator consent.",
      );
    }
  }, [load]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 5000);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setEditing(null);
        setSelected(null);
        setMobile(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const act = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const demo = () =>
    act("demo", async () => {
      await api("/demo", "POST");
      window.location.href = "/dashboard";
    });
  const connectProvider = (provider: "google" | "outlook") =>
    act("connect", async () => {
      const prefix = provider === "google" ? "/auth/google" : "/auth";
      await api(prefix + "/status");
      window.location.href = "/api" + prefix + "/login";
    });
  const connect = () => connectProvider("google");
  const sourceName =
    profile?.provider === "google" ? "Gmail" : "Microsoft Outlook";
  const calendarName =
    profile?.provider === "google" ? "Google Calendar" : "Outlook Calendar";
  const sync = () =>
    act("sync", async () => {
      const result = await api("/sync", "POST");
      await load();
      setToast(result.message);
    });
  const action = (e: Event, action: string) =>
    act(e.id, async () => {
      await api(`/events/${e.id}/${action}`, "POST");
      await load();
      setToast(
        action === "approve"
          ? profile?.demo
            ? "Added to your demo calendar."
            : `Saved to ${calendarName}.`
          : "Suggestion rejected.",
      );
      setSelected(null);
    });
  const approved = events.filter((e) => e.status === "approved"),
    pending = events.filter((e) => e.status === "pending");
  const upcoming = approved
    .filter((e) => e.start && new Date(e.end || e.start) >= new Date())
    .sort((a, b) => Date.parse(a.start!) - Date.parse(b.start!));
  const matches = (e: Event) =>
    (filter === "All" || e.category === filter) &&
    `${e.title} ${e.venue}`.toLowerCase().includes(query.toLowerCase());
  const auth = profile?.authenticated;
  const pageTitle = nav.find((n) => n[0] === initial)?.[1] || "Overview";
  function EventRow({
    event: e,
    review = false,
  }: {
    event: Event;
    review?: boolean;
  }) {
    return (
      <div className="event-row">
        <div className={`date-tile ${color(e.category)}`}>
          <span>
            {e.start
              ? fmt(e.start, { month: "short", day: undefined }, e.timezone)
              : "SET"}
          </span>
          <b>
            {e.start
              ? fmt(e.start, { day: "numeric", month: undefined }, e.timezone)
              : "—"}
          </b>
        </div>
        <div className="event-info">
          <button className="title-button" onClick={() => setSelected(e)}>
            {e.title}
          </button>
          <div className="meta">
            <span>
              <Clock3 size={13} />
              {time(e)}
            </span>
            <span>
              <MapPin size={13} />
              {e.venue || "Venue to confirm"}
            </span>
          </div>
        </div>
        <span className={`tag ${color(e.category)}`}>{e.category}</span>
        {review ? (
          <button
            className="icon-button"
            aria-label={`Review ${e.title}`}
            onClick={() => setEditing(e)}
          >
            <ArrowUpRight size={18} />
          </button>
        ) : (
          <ChevronRight className="muted" size={16} />
        )}
      </div>
    );
  }
  function Empty({
    text = "Nothing here yet. Sync your connected inbox to get started.",
  }: {
    text?: string;
  }) {
    return (
      <div className="empty">
        <Inbox size={30} />
        <b>You’re all caught up</b>
        <p>{text}</p>
      </div>
    );
  }
  function ConnectPanel() {
    return (
      <div className="connect-panel card">
        <div className="outlook-logo">
          <Mail size={27} />
        </div>
        <h2>Your next semester, a little simpler.</h2>
        <p>
          Connect Gmail to turn academic notices into events you can review and
          keep.
        </p>
        <button className="primary" onClick={connect} disabled={!!busy}>
          <Mail size={16} />
          Connect Gmail
        </button>
        <button
          className="secondary"
          onClick={() => connectProvider("outlook")}
          disabled={!!busy}
        >
          Use Microsoft Outlook instead
        </button>
        {profile?.demo_enabled && (
          <button className="text-button" onClick={demo} disabled={!!busy}>
            Explore the interactive demo <ArrowRight size={15} />
          </button>
        )}
        <small>
          <ShieldCheck size={14} />
          Your email stays private. You stay in control.
        </small>
      </div>
    );
  }
  if (initial === "landing")
    return (
      <div className="landing">
        <header className="landing-nav">
          <Link href="/" className="brand">
            <span className="brand-symbol">
              <GraduationCap />
            </span>
            Acad<span>Sync</span>
          </Link>
          <nav>
            <a href="#how">How it works</a>
            <a href="#privacy">Built for students</a>
            <Link href="/dashboard" className="primary">
              Open dashboard <ArrowUpRight size={16} />
            </Link>
          </nav>
        </header>
        {error && (
          <div role="alert" className="error">
            {error}
          </div>
        )}
        <main>
          <section className="hero">
            <div className="hero-copy">
              <span className="eyebrow">
                <span className="live-dot" />
                LESS INBOX. MORE HEADSPACE.
              </span>
              <h1>
                Your semester.
                <br />
                Finally, <em>in sync.</em>
              </h1>
              <p>
                Assignments in your inbox. Exams in another email. Bring every
                academic deadline into one calm, organized calendar.
              </p>
              <div className="hero-actions">
                <button className="primary" onClick={connect} disabled={!!busy}>
                  Get started with Gmail <ArrowRight size={18} />
                </button>
                {profile?.demo_enabled && (
                  <button
                    className="secondary"
                    onClick={demo}
                    disabled={!!busy}
                  >
                    {busy === "demo" ? (
                      <Loader2 className="spin" size={16} />
                    ) : null}
                    Try the demo
                  </button>
                )}
              </div>
              <div className="hero-note">
                <ShieldCheck size={16} />
                Private by design. Every event approved by you.
              </div>
            </div>
            <div className="hero-preview">
              <div className="preview-bar">
                <div className="brand-symbol">
                  <GraduationCap size={20} />
                </div>
                <b>Your week, at a glance</b>
                <span className="tag seminar">All in one place</span>
              </div>
              <div className="preview-heading">
                <span>MAKE ROOM FOR WHAT MATTERS</span>
                <h2>A clearer week ahead.</h2>
              </div>
              {[
                [
                  "MON",
                  "02",
                  "Database design assignment",
                  "Assignment",
                  "11:59 PM",
                ],
                ["TUE", "03", "Sustainability seminar", "Seminar", "2:00 PM"],
                ["THU", "05", "Linear Algebra midterm", "Exam", "10:00 AM"],
              ].map(([day, date, title, cat, t]) => (
                <div className="preview-event" key={day}>
                  <div className="date-tile">
                    <span>{day}</span>
                    <b>{date}</b>
                  </div>
                  <div>
                    <b>{title}</b>
                    <p>{t} · From Gmail</p>
                  </div>
                  <span className={`category-dot ${color(cat)}`} />
                </div>
              ))}
              <div className="preview-bottom">
                <Sparkles size={17} />
                <span>Found in your inbox. Ready for your calendar.</span>
              </div>
              <div className="floating-note">
                <span className="success-circle">
                  <Check size={18} />
                </span>
                <div>
                  <b>One less thing to remember</b>
                  <small>You’re on top of it.</small>
                </div>
              </div>
            </div>
          </section>
          <section id="how" className="how">
            <span className="eyebrow">FROM EMAIL TO EVERYDAY CLARITY</span>
            <h2>A little less admin. A lot more focus.</h2>
            <div className="steps">
              {[
                [
                  Mail,
                  "01",
                  "Connect your inbox",
                  "Securely connect your personal Gmail account.",
                ],
                [
                  Sparkles,
                  "02",
                  "Let notices find you",
                  "AcadSync identifies academic events and dates.",
                ],
                [
                  CheckCheck,
                  "03",
                  "Review, then relax",
                  "Check the details and add events to your calendar.",
                ],
              ].map(([Icon, num, title, description]) => {
                const I = Icon as typeof Mail;
                return (
                  <article key={String(num)}>
                    <span className="step-icon">
                      <I size={24} />
                    </span>
                    <small>{String(num)}</small>
                    <h3>{String(title)}</h3>
                    <p>{String(description)}</p>
                  </article>
                );
              })}
            </div>
          </section>
          <section id="privacy" className="privacy-band">
            <ShieldCheck size={36} />
            <div>
              <h2>Your inbox is personal. We keep it that way.</h2>
              <p>
                Encrypted credentials. Minimal email storage. No calendar
                changes without your review.
              </p>
            </div>
            <Link href="/settings">
              Privacy controls <ArrowRight size={18} />
            </Link>
          </section>
        </main>
        <footer>
          <span>AcadSync</span>
          <p>A little clarity for your academic life.</p>
          <span>Gmail and Outlook. One organized semester.</span>
        </footer>
      </div>
    );
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <Link href="/" className="brand">
          <span className="brand-symbol">
            <GraduationCap />
          </span>
          Acad<span>Sync</span>
        </Link>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav>
          {nav.map(([path, label, Icon]) => (
            <Link
              key={path}
              href={"/" + path}
              className={initial === path ? "active" : ""}
              onClick={() => setMobile(false)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {path === "review" && pending.length > 0 && (
                <b className="nav-count">{pending.length}</b>
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="focus-note">
            <span>✧</span>
            <h4>Make space for learning.</h4>
            <p>We’ll help you keep track of the rest.</p>
          </div>
          <div className="privacy-line">
            <ShieldCheck size={15} />
            Your data, your control
          </div>
          <div className="profile">
            <span className="avatar">
              {(profile?.name || "Student")
                .split(" ")
                .map((n) => n[0])
                .slice(0, 2)
                .join("")}
            </span>
            <div>
              <b>{profile?.name || "Welcome, student"}</b>
              <small>
                {profile?.demo ? "Demo workspace" : "Student workspace"}
              </small>
            </div>
            {auth && (
              <button
                className="icon-button"
                aria-label="Sign out"
                onClick={() =>
                  act("logout", async () => {
                    await api("/logout", "POST");
                    window.location.href = "/";
                  })
                }
              >
                <LogOut size={16} />
              </button>
            )}
          </div>
        </div>
      </aside>
      {mobile && (
        <div className="sidebar-scrim" onClick={() => setMobile(false)} />
      )}
      <div className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            aria-label="Open navigation"
            onClick={() => setMobile(!mobile)}
          >
            <Menu size={22} />
          </button>
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <b>{pageTitle}</b>
          </div>
          <div className="topbar-right">
            <span className="today">
              <CalendarDays size={15} />
              {fmt(new Date().toISOString(), {
                month: "long",
                day: "numeric",
                year: "numeric",
              })}
            </span>
            <Link
              href="/review"
              className="notification"
              aria-label={`${pending.length} pending suggestions`}
            >
              <Bell size={19} />
              {pending.length > 0 && <i />}
            </Link>
            <span className="avatar small">{(profile?.name || "S")[0]}</span>
          </div>
        </header>
        <main className="workspace-main">
          {profile?.demo && (
            <div className="demo-banner">
              <span>
                <span className="live-dot" />
                Demo workspace · Sample notices, real review workflow
              </span>
              <button onClick={connect}>
                Connect your Gmail <ArrowRight size={14} />
              </button>
            </div>
          )}
          {error && (
            <div role="alert" className="error">
              <AlertCircle size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {toast && (
            <div role="status" className="toast">
              <Check size={17} />
              {toast}
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {initial === "dashboard"
                  ? "YOUR ACADEMIC COMMAND CENTER"
                  : "A LITTLE MORE ORGANIZED"}
              </div>
              <h1>
                {initial === "dashboard"
                  ? `A clearer day starts here${profile?.name ? ", " + profile.name.split(" ")[0] : ""}.`
                  : pageTitle}
              </h1>
              <p>
                {
                  (
                    {
                      dashboard:
                        "All your academic moments. One place to stay ahead.",
                      review: "A quick check from you. One less thing to miss.",
                      calendar: "Make time for what’s next.",
                      sources: "Bring your academic world together.",
                      settings:
                        "Your workspace, your preferences, your control.",
                    } as Record<string, string>
                  )[initial]
                }
              </p>
            </div>
            {auth && (
              <button
                className="primary"
                onClick={sync}
                disabled={!!busy || (!profile?.demo && !profile?.connected)}
              >
                <RefreshCw
                  size={16}
                  className={busy === "sync" ? "spin" : ""}
                />
                {busy === "sync" ? "Syncing inbox…" : "Sync now"}
              </button>
            )}
          </div>
          {loading ? (
            <div className="loading">
              <Loader2 className="spin" />
              <p>Getting your workspace ready…</p>
            </div>
          ) : !auth ? (
            <ConnectPanel />
          ) : (
            <>
              {initial === "dashboard" && (
                <>
                  <div className="stats-grid">
                    {[
                      [
                        CalendarDays,
                        "Upcoming events",
                        upcoming.length,
                        "Your calendar, organized",
                        "blue",
                      ],
                      [
                        Sparkles,
                        "Pending review",
                        pending.length,
                        "A quick check from you",
                        "purple",
                      ],
                      [
                        Clock3,
                        "Deadlines this week",
                        upcoming.filter(
                          (e) =>
                            ["Assignment", "Submission", "Deadline"].includes(
                              e.category,
                            ) &&
                            Date.parse(e.start!) < Date.now() + 7 * 86400000,
                        ).length,
                        "Stay one step ahead",
                        "orange",
                      ],
                      [
                        Link2,
                        "Connected sources",
                        profile?.connected ? 1 : 0,
                        profile?.demo ? "Demo mode is active" : sourceName,
                        "green",
                      ],
                    ].map(([Icon, label, value, note, tone]) => {
                      const I = Icon as typeof Mail;
                      return (
                        <div className="stat card" key={String(label)}>
                          <div>
                            <span>{String(label)}</span>
                            <span className={`stat-icon ${tone}`}>
                              <I size={19} />
                            </span>
                          </div>
                          <strong>{String(value).padStart(2, "0")}</strong>
                          <small>{String(note)}</small>
                        </div>
                      );
                    })}
                  </div>
                  <div className="dashboard-grid">
                    <div className="main-column">
                      <section className="card">
                        <div className="card-header">
                          <h2>
                            Upcoming events{" "}
                            <span className="count">{upcoming.length}</span>
                          </h2>
                          <Link href="/calendar">
                            View calendar <ArrowUpRight size={15} />
                          </Link>
                        </div>
                        <div className="section-subtitle">
                          A little preparation goes a long way.
                        </div>
                        {upcoming.length ? (
                          upcoming
                            .slice(0, 4)
                            .map((e) => <EventRow key={e.id} event={e} />)
                        ) : (
                          <Empty />
                        )}
                        <Link className="card-footer-link" href="/calendar">
                          See your full schedule <ArrowRight size={15} />
                        </Link>
                      </section>
                      <section className="card review-preview">
                        <div className="card-header">
                          <h2>
                            <Sparkles size={19} />
                            Ready for your review{" "}
                            <span className="count purple">
                              {pending.length}
                            </span>
                          </h2>
                          <Link href="/review">
                            Review all <ArrowUpRight size={15} />
                          </Link>
                        </div>
                        <div className="section-subtitle">
                          We found these in your inbox. You have the final say.
                        </div>
                        {pending.slice(0, 2).map((e) => (
                          <div className="suggestion" key={e.id}>
                            <div
                              className={`suggestion-icon ${color(e.category)}`}
                            >
                              <BookOpen size={19} />
                            </div>
                            <div>
                              <b>{e.title}</b>
                              <p>
                                {fmt(e.start, {}, e.timezone)} · {time(e)}{" "}
                                <span className="confidence">
                                  {Math.round(e.confidence * 100)}% confidence
                                </span>
                              </p>
                            </div>
                            <button
                              className="secondary compact"
                              onClick={() => setEditing(e)}
                            >
                              Review <ArrowRight size={14} />
                            </button>
                          </div>
                        ))}
                        {!pending.length && (
                          <Empty text="New academic notices will appear here after your next sync." />
                        )}
                      </section>
                      <section className="card">
                        <div className="card-header">
                          <h2>Recently detected notices</h2>
                          <span className="subtle-label">FROM YOUR INBOX</span>
                        </div>
                        {notices.slice(0, 3).map((n) => (
                          <div className="notice" key={n.id}>
                            <span className="mail-icon">
                              <Mail size={17} />
                            </span>
                            <div>
                              <b>{n.title}</b>
                              <p>
                                {n.source} · {fmt(n.received_at)}
                              </p>
                            </div>
                            <span className="detected">
                              <span className="live-dot" />
                              {n.result}
                            </span>
                          </div>
                        ))}
                      </section>
                    </div>
                    <div className="side-column">
                      <section className="card mini-calendar">
                        <MiniCalendar
                          events={approved}
                          month={month}
                          setMonth={setMonth}
                        />
                      </section>
                      <section className="card">
                        <div className="card-header">
                          <h2>Your sources</h2>
                          <Link href="/sources">
                            <ArrowUpRight size={17} />
                          </Link>
                        </div>
                        <div className="source-summary">
                          <div className="outlook-logo small-logo">
                            O<Mail size={19} />
                          </div>
                          <div>
                            <b>{profile?.demo ? "Demo inbox" : sourceName}</b>
                            <small>
                              {profile?.demo
                                ? "Demo source"
                                : profile?.connected
                                  ? "Connected"
                                  : "Not connected"}
                            </small>
                          </div>
                          <span
                            className={`status-dot ${profile?.connected ? "" : "inactive"}`}
                          />
                        </div>
                        <div className="sync-time">
                          <RefreshCw size={13} />
                          {profile?.last_sync
                            ? "Last sync " +
                              fmt(profile.last_sync, {
                                hour: "numeric",
                                minute: "2-digit",
                              })
                            : "Ready when you are"}
                        </div>
                      </section>
                      <section className="tip-card">
                        <span className="tip-icon">✧</span>
                        <span className="eyebrow">A LITTLE PEACE OF MIND</span>
                        <h3>
                          More focus.
                          <br />
                          Fewer missed moments.
                        </h3>
                        <p>
                          Your inbox shouldn’t be your to-do list. Let your
                          calendar do the remembering.
                        </p>
                        <div className="tip-line" />
                      </section>
                    </div>
                  </div>
                </>
              )}
              {initial === "review" && (
                <>
                  <div className="toolbar">
                    <div className="tabs">
                      <button className="selected">
                        Pending review <span>{pending.length}</span>
                      </button>
                      <span className="muted">
                        {events.filter((e) => e.status === "rejected").length}{" "}
                        rejected · {approved.length} approved
                      </span>
                    </div>
                    <SearchBox query={query} setQuery={setQuery} />
                  </div>
                  <div className="review-grid">
                    {pending.filter(matches).map((e) => (
                      <article className="card review-card" key={e.id}>
                        <div className="review-card-top">
                          <span className={`tag ${color(e.category)}`}>
                            {e.category}
                          </span>
                          <span className="confidence">
                            <Sparkles size={13} />
                            {Math.round(e.confidence * 100)}% confidence
                          </span>
                        </div>
                        <h2>{e.title}</h2>
                        <p className="review-description">{e.description}</p>
                        <div className="detail-line">
                          <CalendarDays size={16} />
                          {fmt(e.start, { year: "numeric" }, e.timezone)} ·{" "}
                          {time(e)}
                        </div>
                        <div className="detail-line">
                          <MapPin size={16} />
                          {e.venue || "Venue to confirm"}
                        </div>
                        <div className="detail-line">
                          <Mail size={16} />
                          {e.source}{" "}
                          {e.source_url && (
                            <a
                              href={e.source_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <ExternalLink size={13} />
                            </a>
                          )}
                        </div>
                        {e.warnings.length > 0 && (
                          <div className="warning">
                            <AlertCircle size={15} />
                            <span>{e.warnings.join(" ")}</span>
                          </div>
                        )}
                        <div className="review-actions">
                          <button
                            className="icon-button"
                            disabled={!!busy}
                            aria-label={`Reject ${e.title}`}
                            onClick={() => action(e, "reject")}
                          >
                            <X size={18} />
                          </button>
                          <button
                            className="secondary"
                            onClick={() => setEditing(e)}
                          >
                            <Pencil size={14} />
                            Edit
                          </button>
                          <button
                            className="primary"
                            disabled={!!busy || !e.start}
                            onClick={() => action(e, "approve")}
                          >
                            <Check size={16} />
                            {busy === e.id
                              ? "Saving…"
                              : e.calendar_synced
                                ? "Approve update"
                                : "Approve"}
                          </button>
                        </div>
                      </article>
                    ))}
                  </div>
                  {!pending.filter(matches).length && (
                    <div className="card">
                      <Empty text="No matching suggestions. Sync your inbox to find new academic notices." />
                    </div>
                  )}
                </>
              )}
              {initial === "calendar" && (
                <>
                  <div className="toolbar">
                    <div className="calendar-controls">
                      <button
                        aria-label="Previous period"
                        className="icon-button"
                        onClick={() =>
                          setMonth(
                            new Date(
                              month.getFullYear(),
                              month.getMonth() - (view === "Month" ? 1 : 0),
                              month.getDate() - (view === "Week" ? 7 : 0),
                            ),
                          )
                        }
                      >
                        <ChevronLeft size={18} />
                      </button>
                      <h2>
                        {month.toLocaleDateString("en-US", {
                          month: "long",
                          year: "numeric",
                        })}
                      </h2>
                      <button
                        aria-label="Next period"
                        className="icon-button"
                        onClick={() =>
                          setMonth(
                            new Date(
                              month.getFullYear(),
                              month.getMonth() + (view === "Month" ? 1 : 0),
                              month.getDate() + (view === "Week" ? 7 : 0),
                            ),
                          )
                        }
                      >
                        <ChevronRight size={18} />
                      </button>
                      <button
                        className="secondary compact"
                        onClick={() => setMonth(new Date())}
                      >
                        Today
                      </button>
                    </div>
                    <div className="tabs">
                      {["Month", "Week", "List"].map((v) => (
                        <button
                          key={v}
                          className={view === v ? "selected" : ""}
                          onClick={() => setView(v)}
                        >
                          {v}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="filter-bar">
                    <SlidersHorizontal size={16} />
                    {["All", ...categories].map((c) => (
                      <button
                        key={c}
                        className={filter === c ? "active" : ""}
                        onClick={() => setFilter(c)}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                  <section className="card calendar-card">
                    {view === "List" ? (
                      <>
                        {approved
                          .filter(matches)
                          .sort(
                            (a, b) =>
                              Date.parse(a.start!) - Date.parse(b.start!),
                          )
                          .map((e) => (
                            <EventRow key={e.id} event={e} />
                          ))}
                        {!approved.filter(matches).length && <Empty />}
                      </>
                    ) : (
                      <BigCalendar
                        events={approved.filter(matches)}
                        month={month}
                        view={view}
                        select={setSelected}
                        zone={profile?.timezone}
                      />
                    )}
                  </section>
                  <p className="calendar-note">
                    <span className="live-dot" />
                    {profile?.demo
                      ? "Demo calendar · No changes are sent to external calendars"
                      : `Approved events are saved to ${calendarName}`}{" "}
                    · {profile?.timezone}
                  </p>
                </>
              )}
              {initial === "sources" && (
                <>
                  <div className="sources-grid">
                    {[
                      {
                        name: "Gmail",
                        provider: "google",
                        description:
                          "Detect academic notices in Gmail and save approved events to Google Calendar.",
                      },
                      {
                        name: "Microsoft Outlook",
                        provider: "outlook",
                        description:
                          "Turn Outlook emails into reviewed events in your Outlook calendar.",
                      },
                      {
                        name: "Microsoft Teams",
                        provider: null,
                        description:
                          "Catch the important dates in your class conversations.",
                      },
                      {
                        name: "Moodle",
                        provider: null,
                        description:
                          "Keep course assignments and learning deadlines in sync.",
                      },
                    ].map((source, i) => {
                      const connected =
                        !profile?.demo &&
                        profile?.connected &&
                        profile.provider === source.provider;
                      return (
                        <section
                          key={source.name}
                          className={`card source-card ${source.provider ? "" : "coming-soon"}`}
                        >
                          <div className="source-card-top">
                            <div className={`provider-logo provider-${i}`}>
                              <Mail size={28} />
                            </div>
                            <span
                              className={`tag ${connected ? "seminar" : "neutral"}`}
                            >
                              {!source.provider
                                ? "Coming soon"
                                : connected
                                  ? "Connected"
                                  : "Available"}
                            </span>
                          </div>
                          <h2>{source.name}</h2>
                          <p>{source.description}</p>
                          {source.provider ? (
                            <>
                              <div className="source-account">
                                {connected
                                  ? profile?.email
                                  : `Connect your ${source.name} account`}
                                <small>
                                  {connected && profile?.last_sync
                                    ? "Last synced " +
                                      fmt(profile.last_sync, {
                                        hour: "numeric",
                                        minute: "2-digit",
                                      })
                                    : "No sync yet"}
                                </small>
                              </div>
                              <button
                                className={connected ? "secondary" : "primary"}
                                disabled={!!busy}
                                onClick={() =>
                                  connected
                                    ? sync()
                                    : connectProvider(
                                        source.provider as "google" | "outlook",
                                      )
                                }
                              >
                                {connected ? (
                                  <RefreshCw size={16} />
                                ) : (
                                  <Link2 size={16} />
                                )}{" "}
                                {connected ? "Sync " : "Connect "}
                                {source.name}
                              </button>
                            </>
                          ) : (
                            <button className="secondary" disabled>
                              On the horizon
                            </button>
                          )}
                        </section>
                      );
                    })}
                  </div>
                  <div className="permission-note">
                    <ShieldCheck size={25} />
                    <div>
                      <h3>Connected with your permission.</h3>
                      <p>
                        Gmail and Outlook use your consent to read academic
                        notices and save approved events. Each connected account
                        opens its own workspace; switching accounts does not
                        merge data. Google test accounts may need reconnection
                        after seven days. College Outlook accounts may require
                        administrator approval.
                      </p>
                    </div>
                  </div>
                </>
              )}
              {initial === "settings" && (
                <div className="settings-stack">
                  <section className="card settings-card">
                    <h2>Workspace preferences</h2>
                    <p>
                      New notices are interpreted in your selected timezone.
                    </p>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        act("settings", async () => {
                          await api("/settings", "PATCH", { timezone: tz });
                          await load();
                          setToast("Preferences saved.");
                        });
                      }}
                    >
                      <label>
                        Timezone
                        <select
                          value={tz}
                          onChange={(e) => setTz(e.target.value)}
                        >
                          {Array.from(
                            new Set([
                              tz,
                              "Asia/Kolkata",
                              "UTC",
                              "Europe/London",
                              "America/New_York",
                              "America/Los_Angeles",
                              "Asia/Singapore",
                              "Australia/Sydney",
                            ]),
                          ).map((z) => (
                            <option key={z}>{z}</option>
                          ))}
                        </select>
                      </label>
                      <button className="primary" disabled={!!busy}>
                        Save preferences
                      </button>
                    </form>
                  </section>
                  <section className="card settings-card">
                    <h2>Account & permissions</h2>
                    <p>{profile?.email}</p>
                    <div className="permission-list">
                      <span>
                        <Check size={16} />
                        Read your basic account profile
                      </span>
                      <span>
                        <Check size={16} />
                        Read emails to detect academic notices
                      </span>
                      <span>
                        <Check size={16} />
                        Save approved events to your calendar
                      </span>
                    </div>
                    <p>
                      Tokens are encrypted on the server. Raw email bodies are
                      processed transiently; event details and relevant notice
                      metadata are retained. Disconnecting removes stored
                      credentials. To revoke provider consent, visit{" "}
                      <a
                        href={
                          profile?.provider === "google"
                            ? "https://myaccount.google.com/connections"
                            : "https://myapplications.microsoft.com/"
                        }
                        target="_blank"
                        rel="noreferrer"
                      >
                        {profile?.provider === "google"
                          ? "Google Account connections"
                          : "Microsoft My Apps"}
                      </a>
                      .
                    </p>
                    <div className="button-row">
                      <button
                        className="secondary"
                        onClick={() =>
                          connectProvider(profile?.provider || "google")
                        }
                      >
                        Reconnect {sourceName}
                      </button>
                      <button
                        className="secondary"
                        disabled={!!busy || !profile?.connected}
                        onClick={() =>
                          act("disconnect", async () => {
                            await api("/disconnect", "POST");
                            await load();
                            setToast(
                              "Account disconnected. Stored credentials removed.",
                            );
                          })
                        }
                      >
                        Disconnect account
                      </button>
                      <button
                        className="text-button"
                        disabled={!!busy}
                        onClick={() =>
                          act("reset", async () => {
                            await api("/reset-sync", "POST");
                            await load();
                            setToast(
                              "Sync reset. The next sync will scan the last 30 days.",
                            );
                          })
                        }
                      >
                        Reset sync
                      </button>
                    </div>
                  </section>
                  <section className="card settings-card danger-zone">
                    <h2>Delete your AcadSync data</h2>
                    <p>
                      Permanently remove your profile, sessions, stored
                      credentials, notices and event records. Events already
                      saved in your external calendar remain there.
                    </p>
                    <button
                      className="danger"
                      disabled={!!busy}
                      onClick={() => {
                        if (
                          window.confirm(
                            "Permanently delete all your AcadSync data? This cannot be undone. External calendar events will remain.",
                          )
                        )
                          act("delete", async () => {
                            await api("/account", "DELETE");
                            window.location.href = "/";
                          });
                      }}
                    >
                      <Trash2 size={16} />
                      Delete my data
                    </button>
                  </section>
                </div>
              )}
            </>
          )}
          <footer className="workspace-footer">
            <span>Less noise. More focus.</span>
            <span>
              <ShieldCheck size={13} />
              Thoughtfully built for your academic life
            </span>
          </footer>
        </main>
      </div>
      {editing && (
        <EventEditor
          event={editing}
          busy={!!busy}
          close={() => setEditing(null)}
          save={(data) =>
            act("edit", async () => {
              await api("/events/" + editing.id, "PATCH", data);
              await load();
              setEditing(null);
              setToast("Event details updated. Ready for approval.");
            })
          }
        />
      )}
      {selected && (
        <div className="modal-backdrop" onClick={() => setSelected(null)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="event-title"
            className="modal"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              autoFocus
              className="modal-close icon-button"
              aria-label="Close details"
              onClick={() => setSelected(null)}
            >
              <X />
            </button>
            <span className={`tag ${color(selected.category)}`}>
              {selected.category}
            </span>
            <h2 id="event-title">{selected.title}</h2>
            <p>{selected.description}</p>
            <div className="detail-line">
              <CalendarDays size={17} />
              {fmt(
                selected.start,
                { year: "numeric" },
                selected.timezone,
              )} · {time(selected)}
            </div>
            <div className="detail-line">
              <MapPin size={17} />
              {selected.venue || "Venue to confirm"}
            </div>
            <p>
              {selected.timezone} · {selected.status}
            </p>
            {selected.source_url && (
              <a
                className="text-button"
                href={selected.source_url}
                target="_blank"
                rel="noreferrer"
              >
                Open original notice <ExternalLink size={15} />
              </a>
            )}
            {selected.status === "pending" && (
              <button
                className="primary"
                onClick={() => {
                  setEditing(selected);
                  setSelected(null);
                }}
              >
                Review event <ArrowRight size={16} />
              </button>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function SearchBox({
  query,
  setQuery,
}: {
  query: string;
  setQuery: (q: string) => void;
}) {
  return (
    <label className="search">
      <Search size={16} />
      <input
        placeholder="Search events…"
        aria-label="Search events"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
    </label>
  );
}
function daysFor(month: Date, week = false) {
  const first = week
    ? new Date(month)
    : new Date(month.getFullYear(), month.getMonth(), 1);
  first.setDate(first.getDate() - ((first.getDay() + 6) % 7));
  return Array.from(
    { length: week ? 7 : 42 },
    (_, i) =>
      new Date(first.getFullYear(), first.getMonth(), first.getDate() + i),
  );
}
function dateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function eventDay(e: Event, zone?: string) {
  return e.start
    ? new Intl.DateTimeFormat("en-CA", {
        timeZone: zone || e.timezone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date(e.start))
    : "";
}
function MiniCalendar({
  events,
  month,
  setMonth,
}: {
  events: Event[];
  month: Date;
  setMonth: (d: Date) => void;
}) {
  return (
    <>
      <div className="mini-calendar-head">
        <h2>
          {month.toLocaleDateString("en-US", {
            month: "long",
            year: "numeric",
          })}
        </h2>
        <div>
          <button
            aria-label="Previous month"
            onClick={() =>
              setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))
            }
          >
            <ChevronLeft size={16} />
          </button>
          <button
            aria-label="Next month"
            onClick={() =>
              setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))
            }
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>
      <div className="mini-grid">
        {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
          <span className="weekday" key={i}>
            {d}
          </span>
        ))}
        {daysFor(month).map((d) => (
          <Link
            href="/calendar"
            key={d.toISOString()}
            className={`${d.getMonth() !== month.getMonth() ? "off-month" : ""} ${dateKey(d) === dateKey(new Date()) ? "today-cell" : ""}`}
          >
            <span>{d.getDate()}</span>
            {events.some((e) => eventDay(e) === dateKey(d)) && <i />}
          </Link>
        ))}
      </div>
      <div className="mini-legend">
        <span className="category-dot assignment" />
        Assignment
        <span className="category-dot exam" />
        Exam
        <span className="category-dot seminar" />
        Seminar
      </div>
    </>
  );
}
function BigCalendar({
  events,
  month,
  view,
  select,
  zone,
}: {
  events: Event[];
  month: Date;
  view: string;
  select: (e: Event) => void;
  zone?: string;
}) {
  return (
    <div className={`big-calendar ${view === "Week" ? "week-view" : ""}`}>
      <div className="calendar-weekdays">
        {[
          "Monday",
          "Tuesday",
          "Wednesday",
          "Thursday",
          "Friday",
          "Saturday",
          "Sunday",
        ].map((d) => (
          <b key={d}>{d}</b>
        ))}
      </div>
      <div className="calendar-days">
        {daysFor(month, view === "Week").map((d) => (
          <div
            key={d.toISOString()}
            className={`day-cell ${d.getMonth() !== month.getMonth() ? "off-month" : ""}`}
          >
            <span
              className={
                dateKey(d) === dateKey(new Date()) ? "today-number" : ""
              }
            >
              {d.getDate()}
            </span>
            {events
              .filter((e) => eventDay(e, zone) === dateKey(d))
              .map((e) => (
                <button
                  key={e.id}
                  className={`calendar-event ${color(e.category)}`}
                  onClick={() => select(e)}
                >
                  <b>{e.title}</b>
                  <small>{time(e)}</small>
                </button>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}
function localInput(value: string | null) {
  if (!value) return "";
  const d = new Date(value);
  return `${dateKey(d)}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
function EventEditor({
  event,
  busy,
  close,
  save,
}: {
  event: Event;
  busy: boolean;
  close: () => void;
  save: (e: Event) => void;
}) {
  const [draft, setDraft] = useState(event),
    [start, setStart] = useState(localInput(event.start)),
    [end, setEnd] = useState(localInput(event.end));
  const field = (key: string, value: unknown) =>
    setDraft({ ...draft, [key]: value });
  return (
    <div className="modal-backdrop">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-title"
        className="modal editor"
      >
        <button
          className="modal-close icon-button"
          aria-label="Close editor"
          onClick={close}
        >
          <X />
        </button>
        <span className="eyebrow">YOU HAVE THE FINAL SAY</span>
        <h2 id="edit-title">Review event details</h2>
        <p>Check the details before adding this event to your calendar.</p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save({
              ...draft,
              start: start ? new Date(start).toISOString() : null,
              end: end ? new Date(end).toISOString() : null,
            });
          }}
        >
          <label>
            Event title
            <input
              autoFocus
              required
              maxLength={300}
              value={draft.title}
              onChange={(e) => field("title", e.target.value)}
            />
          </label>
          <div className="form-two">
            <label>
              Starts
              <input
                required
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </label>
            <label>
              Ends
              <input
                required
                type="datetime-local"
                min={start}
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </label>
          </div>
          <small className="form-help">
            Times above use this device’s timezone (
            {Intl.DateTimeFormat().resolvedOptions().timeZone}). Event timezone:{" "}
            {draft.timezone}.
          </small>
          <div className="form-two">
            <label>
              Category
              <select
                value={draft.category}
                onChange={(e) => field("category", e.target.value)}
              >
                {categories.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            <label>
              Venue
              <input
                value={draft.venue}
                onChange={(e) => field("venue", e.target.value)}
              />
            </label>
          </div>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={draft.all_day}
              onChange={(e) => field("all_day", e.target.checked)}
            />
            All-day event (midnight to midnight in event timezone)
          </label>
          <label>
            Description
            <textarea
              rows={3}
              maxLength={2000}
              value={draft.description}
              onChange={(e) => field("description", e.target.value)}
            />
          </label>
          {draft.warnings.length > 0 && (
            <div className="warning">{draft.warnings.join(" ")}</div>
          )}
          <div className="modal-actions">
            <button type="button" className="secondary" onClick={close}>
              Cancel
            </button>
            <button className="primary" disabled={busy}>
              <Check size={16} />
              {busy ? "Saving…" : "Save changes"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
