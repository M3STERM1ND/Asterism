"use client";

import { useCallback, useEffect, useState } from "react";
import type { Session as AuthSession } from "@supabase/supabase-js";
import { configured, supabase, type Feedback, type Profile, type Session } from "@/lib/supabase";

// The Asterism portal on Supabase. Coaches follow their linked patients; patients pick a coach.
// Every query runs as the signed-in person, and row-level security decides what comes back.

const field = "w-full rounded-xl border border-line bg-night px-4 py-3 text-ivory outline-none focus:border-gold";
const button = "rounded-full bg-gold px-6 py-3 font-semibold text-night transition-transform hover:-translate-y-0.5 disabled:opacity-50";
const ghost = "rounded-full border border-line px-5 py-2.5 text-ivory hover:border-ivory";

function Shell({ children, profile, onSignOut }: { children: React.ReactNode; profile?: Profile | null; onSignOut?: () => void }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line/60">
        <div className="mx-auto flex h-[72px] max-w-[1100px] items-center justify-between px-6">
          <a href="/" className="font-display text-2xl">✦ Asterism</a>
          {profile && (
            <div className="flex items-center gap-4 text-base text-mist">
              <span>{profile.display_name} · {profile.role}</span>
              <button className={ghost} onClick={onSignOut}>Log out</button>
            </div>
          )}
        </div>
      </header>
      <main className="mx-auto max-w-[1100px] px-6 py-16">{children}</main>
    </div>
  );
}

function Notice({ text, bad }: { text: string; bad?: boolean }) {
  if (!text) return null;
  return <p className={`mb-8 rounded-xl border px-4 py-3 ${bad ? "border-red-400/60 text-red-200" : "border-gold/50 text-ivory"}`}>{text}</p>;
}

/* ------------------------------------------------------------------ sign in / sign up */
function Auth({ onMessage }: { onMessage: (text: string, bad?: boolean) => void }) {
  const [mode, setMode] = useState<"in" | "up">("in");
  const [form, setForm] = useState({ email: "", password: "", username: "", display_name: "", role: "patient", specialty: "" });
  const [busy, setBusy] = useState(false);
  const set = (key: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm({ ...form, [key]: e.target.value });

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    const { error } = mode === "in"
      ? await supabase.auth.signInWithPassword({ email: form.email, password: form.password })
      : await supabase.auth.signUp({
          email: form.email, password: form.password,
          options: { data: { username: form.username.toLowerCase(), display_name: form.display_name, role: form.role, specialty: form.specialty } },
        });
    setBusy(false);
    if (error) onMessage(error.message, true);
    else if (mode === "up") onMessage("Account created. If you are asked to confirm your email, do that, then log in.");
  }

  return (
    <div className="mx-auto max-w-[460px]">
      <h1 className="font-display text-5xl">{mode === "in" ? "Welcome back." : "Join Asterism."}</h1>
      <p className="mt-4 text-mist">Patients play the game at home. Coaches follow their progress here.</p>
      <form onSubmit={submit} className="mt-10 space-y-4">
        {mode === "up" && (
          <>
            <select className={field} value={form.role} onChange={set("role")} aria-label="I am a">
              <option value="patient">I am a patient</option>
              <option value="coach">I am a coach</option>
            </select>
            <input className={field} placeholder="Username (3-20 letters, numbers or _)" value={form.username} onChange={set("username")} required pattern="[a-zA-Z0-9_]{3,20}" />
            <input className={field} placeholder="Your name" value={form.display_name} onChange={set("display_name")} required />
            {form.role === "coach" && <input className={field} placeholder="Specialty, e.g. stroke rehab" value={form.specialty} onChange={set("specialty")} />}
          </>
        )}
        <input className={field} type="email" placeholder="Email" value={form.email} onChange={set("email")} required autoComplete="email" />
        <input className={field} type="password" placeholder="Password (6+ characters)" value={form.password} onChange={set("password")} required minLength={6}
          autoComplete={mode === "in" ? "current-password" : "new-password"} />
        <button className={`${button} w-full`} disabled={busy}>{busy ? "One moment" : mode === "in" ? "Log in" : "Create account"}</button>
      </form>
      <button className="mt-6 text-mist underline decoration-gold underline-offset-4" onClick={() => setMode(mode === "in" ? "up" : "in")}>
        {mode === "in" ? "New here? Create an account" : "Have an account? Log in"}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ shared pieces */
function SessionTable({ sessions }: { sessions: Session[] }) {
  const [video, setVideo] = useState<string | null>(null);
  async function play(path: string) {
    const { data, error } = await supabase.storage.from("session-videos").createSignedUrl(path, 3600);
    if (!error) setVideo(data.signedUrl);
  }
  if (!sessions.length) return <p className="text-mist">No sessions yet. They appear here after the game uploads them.</p>;
  return (
    <div>
      {video && <video src={video} controls autoPlay className="mb-8 w-full rounded-2xl border border-line" />}
      <div className="overflow-x-auto rounded-2xl border border-line">
        <table className="w-full text-left text-base">
          <thead className="text-mist">
            <tr>{["Played", "Battle", "Result", "Stars", "Error", "Straightness", "Leans", "Pain", ""].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} className="border-t border-line">
                <td className="px-4 py-3">{new Date(s.played_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</td>
                <td className="px-4 py-3">{s.constellation}</td>
                <td className="px-4 py-3">{s.result}</td>
                <td className="px-4 py-3">{s.row["stars hit"] || "-"}</td>
                <td className="px-4 py-3">{s.row["avg error sw"] || "-"}</td>
                <td className="px-4 py-3">{s.row["straightness"] || "-"}</td>
                <td className="px-4 py-3">{s.row["lean warnings"] || "0"}</td>
                <td className={`px-4 py-3 ${Number(s.row["pain"]) >= 4 ? "font-semibold text-red-300" : ""}`}>{s.row["pain"] || "-"}</td>
                <td className="px-4 py-3">{s.video_path && <button className="text-gold underline underline-offset-4" onClick={() => play(s.video_path!)}>Watch</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FeedbackList({ items, names }: { items: Feedback[]; names: Record<string, string> }) {
  if (!items.length) return <p className="text-mist">No feedback yet.</p>;
  return (
    <ul className="space-y-3">
      {items.map((f) => (
        <li key={f.id} className="rounded-2xl border border-line p-5">
          <p className="text-sm text-mist">{names[f.coach_id] ?? "Your coach"} · {new Date(f.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</p>
          <p className="mt-2 max-w-[65ch] whitespace-pre-wrap">{f.text}</p>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ coach */
function CoachView({ me, refresh, onMessage }: { me: Profile; refresh: () => void; onMessage: (t: string, bad?: boolean) => void }) {
  const [patients, setPatients] = useState<Profile[]>([]);
  const [chosen, setChosen] = useState<Profile | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [notes, setNotes] = useState<Feedback[]>([]);
  const [text, setText] = useState("");

  useEffect(() => {
    (async () => {
      const { data: links } = await supabase.from("links").select("patient_id").eq("coach_id", me.id);
      const ids = (links ?? []).map((l) => l.patient_id);
      if (!ids.length) return setPatients([]);
      const { data } = await supabase.from("profiles").select("*").in("id", ids).order("display_name");
      setPatients((data as Profile[]) ?? []);
    })();
  }, [me.id]);

  const open = useCallback(async (p: Profile) => {
    setChosen(p);
    const [{ data: s }, { data: f }] = await Promise.all([
      supabase.from("sessions").select("*").eq("patient_id", p.id).order("played_at", { ascending: false }),
      supabase.from("feedback").select("*").eq("patient_id", p.id).eq("coach_id", me.id).order("created_at", { ascending: false }),
    ]);
    setSessions((s as Session[]) ?? []);
    setNotes((f as Feedback[]) ?? []);
  }, [me.id]);

  async function toggleStatus() {
    const status = me.status === "open" ? "closed" : "open";
    const { error } = await supabase.from("profiles").update({ status }).eq("id", me.id);
    if (error) onMessage(error.message, true);
    else { onMessage(status === "open" ? "You are open: new patients can link to you." : "You are closed: no new patients can link to you."); refresh(); }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!chosen || !text.trim()) return;
    const { error } = await supabase.from("feedback").insert({ coach_id: me.id, patient_id: chosen.id, text: text.trim() });
    if (error) return onMessage(error.message, true);
    setText("");
    onMessage(`Feedback sent to ${chosen.display_name}. They see it when they log in here.`);
    open(chosen);
  }

  return (
    <div className="grid gap-12 md:grid-cols-[300px_1fr]">
      <aside>
        <h1 className="font-display text-4xl">Your patients</h1>
        <div className="mt-6 rounded-2xl border border-line p-5">
          <p className="text-sm text-mist">Status</p>
          <p className="mt-1 text-xl">{me.status === "open" ? "Open to new patients" : "Closed to new patients"}</p>
          <button className={`${ghost} mt-4`} onClick={toggleStatus}>Set to {me.status === "open" ? "closed" : "open"}</button>
        </div>
        <ul className="mt-6 space-y-2">
          {patients.map((p) => (
            <li key={p.id}>
              <button onClick={() => open(p)} className={`w-full rounded-xl border px-4 py-3 text-left ${chosen?.id === p.id ? "border-gold" : "border-line hover:border-ivory"}`}>
                {p.display_name} <span className="text-mist">@{p.username}</span>
              </button>
            </li>
          ))}
          {!patients.length && <li className="text-mist">No patients yet. Patients find you in the catalog while you are open.</li>}
        </ul>
      </aside>
      <section>
        {chosen ? (
          <>
            <h2 className="font-display text-4xl">{chosen.display_name}</h2>
            <h3 className="mb-4 mt-10 text-xl">Sessions</h3>
            <SessionTable sessions={sessions} />
            <h3 className="mb-4 mt-12 text-xl">Write feedback</h3>
            <form onSubmit={send} className="space-y-4">
              <textarea className={`${field} min-h-[120px]`} value={text} onChange={(e) => setText(e.target.value)} placeholder="What went well, and one thing to try next time" maxLength={2000} required />
              <button className={button}>Send feedback</button>
            </form>
            <h3 className="mb-4 mt-12 text-xl">Sent so far</h3>
            <FeedbackList items={notes} names={{ [me.id]: me.display_name }} />
          </>
        ) : (
          <p className="text-mist">Choose a patient to see their sessions, watch replays and write feedback.</p>
        )}
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------ patient */
function PatientView({ me, onMessage }: { me: Profile; onMessage: (t: string, bad?: boolean) => void }) {
  const [coaches, setCoaches] = useState<Profile[]>([]);
  const [myCoach, setMyCoach] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [notes, setNotes] = useState<Feedback[]>([]);

  const load = useCallback(async () => {
    const [{ data: c }, { data: l }, { data: s }, { data: f }] = await Promise.all([
      supabase.from("profiles").select("*").eq("role", "coach").order("status").order("display_name"),
      supabase.from("links").select("coach_id").eq("patient_id", me.id).maybeSingle(),
      supabase.from("sessions").select("*").eq("patient_id", me.id).order("played_at", { ascending: false }),
      supabase.from("feedback").select("*").eq("patient_id", me.id).order("created_at", { ascending: false }),
    ]);
    setCoaches((c as Profile[]) ?? []);
    setMyCoach(l?.coach_id ?? null);
    setSessions((s as Session[]) ?? []);
    setNotes((f as Feedback[]) ?? []);
  }, [me.id]);

  useEffect(() => { load(); }, [load]);

  async function link(coach: Profile) {
    const { error } = await supabase.from("links").upsert({ patient_id: me.id, coach_id: coach.id });
    if (error) onMessage(`${coach.display_name} isn't taking new patients right now.`, true);
    else { onMessage(`You are linked to ${coach.display_name}.`); load(); }
  }

  async function leave() {
    await supabase.from("links").delete().eq("patient_id", me.id);
    onMessage("You no longer have a coach.");
    load();
  }

  const names = Object.fromEntries(coaches.map((c) => [c.id, c.display_name]));
  return (
    <div>
      <h1 className="font-display text-5xl">Hello, {me.display_name}.</h1>
      <div className="mt-10 grid gap-4 md:grid-cols-2">
        <a href="/play" className="group rounded-3xl border border-gold bg-night-2 p-8 transition-transform hover:-translate-y-0.5">
          <p className="font-display text-3xl">Play in your browser</p>
          <p className="mt-3 text-mist">Reach practice with your webcam, right here. Each round saves to your account.</p>
          <p className="mt-6 font-semibold text-gold">Start practice →</p>
        </a>
        <div className="rounded-3xl border border-line p-8">
          <p className="font-display text-3xl">The full game</p>
          <p className="mt-3 text-mist">
            Battles, blocking, safe-reach calibration and the lean guard run on your computer. Download it from{" "}
            <a className="text-ivory underline decoration-gold underline-offset-4" href="https://github.com/M3STERM1ND/Asterism">GitHub</a>,
            then sign in with this same email in the game. Your battles upload here by themselves.
          </p>
        </div>
      </div>
      <h2 className="mb-4 mt-14 text-xl">From your coach</h2>
      <FeedbackList items={notes} names={names} />
      <h2 className="mb-4 mt-14 text-xl">Your sessions</h2>
      <SessionTable sessions={sessions} />
      <h2 className="mb-4 mt-14 text-xl">Coach catalog</h2>
      <div className="grid gap-4 md:grid-cols-2">
        {coaches.map((c) => (
          <article key={c.id} className={`rounded-2xl border p-6 ${myCoach === c.id ? "border-gold" : "border-line"}`}>
            <div className="flex items-center justify-between gap-4">
              <h3 className="font-display text-2xl">{c.display_name}</h3>
              <span className={`rounded-full px-3 py-1 text-sm ${c.status === "open" ? "bg-gold/15 text-gold" : "bg-line text-mist"}`}>{c.status}</span>
            </div>
            <p className="mt-2 text-mist">{c.specialty || "Coach"}</p>
            <div className="mt-5">
              {myCoach === c.id ? (
                <button className={ghost} onClick={leave}>Leave this coach</button>
              ) : c.status === "open" ? (
                <button className={button} onClick={() => link(c)}>Link to {c.display_name}</button>
              ) : (
                <button className={ghost} disabled>Not taking patients</button>
              )}
            </div>
          </article>
        ))}
        {!coaches.length && <p className="text-mist">No coaches have joined yet.</p>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ page */
export default function Portal() {
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [me, setMe] = useState<Profile | null>(null);
  const [ready, setReady] = useState(false);
  const [message, setMessage] = useState({ text: "", bad: false });
  const say = (text: string, bad = false) => setMessage({ text, bad });

  const loadProfile = useCallback(async (session: AuthSession | null) => {
    if (!session) return setMe(null);
    const { data } = await supabase.from("profiles").select("*").eq("id", session.user.id).single();
    setMe(data as Profile);
  }, []);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => { setAuth(data.session); loadProfile(data.session).then(() => setReady(true)); });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, session) => { setAuth(session); loadProfile(session); });
    return () => sub.subscription.unsubscribe();
  }, [loadProfile]);

  async function signOut() {
    await supabase.auth.signOut();
    say("Logged out.");
  }

  if (!configured) {
    return (
      <Shell>
        <Notice bad text="The portal isn't connected yet: add NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY in Vercel > Settings > Environment Variables, then redeploy." />
      </Shell>
    );
  }
  if (!ready) return <Shell><p className="text-mist">Loading</p></Shell>;
  return (
    <Shell profile={me} onSignOut={signOut}>
      <Notice text={message.text} bad={message.bad} />
      {!auth || !me ? (
        <Auth onMessage={say} />
      ) : me.role === "coach" ? (
        <CoachView me={me} refresh={() => loadProfile(auth)} onMessage={say} />
      ) : (
        <PatientView me={me} onMessage={say} />
      )}
    </Shell>
  );
}
