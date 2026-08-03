import { useEffect, useRef, useState } from "react";
import { onAuthStateChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { auth, googleProvider } from "./firebase";

type Msg = { role: "user" | "agent"; text: string };
type Snapshot = {
  phase?: string;
  spec?: { site_name?: string };
  pages?: string[];
  score?: number;
};

const PHASE_LABEL: Record<string, string> = {
  interviewing: "Interviewing",
  planning: "Planning your site…",
  writing: "Writing pages…",
  critiquing: "Reviewing quality…",
  done: "Draft ready",
};

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, phase]);

  async function send() {
    if (!user || !input.trim() || busy) return;
    const text = input.trim();
    setInput("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);

    try {
      const token = await user.getIdToken();
      const res = await fetch("/agent/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        // one thread per user for now — later: one per project
        body: JSON.stringify({ thread_id: `u-${user.uid}`, message: text }),
      });
      if (!res.ok || !res.body) throw new Error(`agent said ${res.status}`);

      // parse the SSE stream: events arrive as "event: X\ndata: {...}\n\n"
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const evt of events) {
          const type = evt.match(/^event: (.+)$/m)?.[1];
          const data = JSON.parse(evt.match(/^data: (.+)$/m)?.[1] ?? "{}");
          if (type === "node") {
            if (data.phase) setPhase(data.phase);
            if (data.reply) setMsgs((m) => [...m, { role: "agent", text: data.reply }]);
          } else if (type === "done") {
            setSnapshot(data);
            setPhase(data.phase ?? null);
          }
        }
      }
    } catch (e) {
      setMsgs((m) => [
        ...m,
        { role: "agent", text: `⚠️ ${e instanceof Error ? e.message : e} — is the agent running on :8001?` },
      ]);
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <main className="shell">Loading…</main>;

  if (!user) {
    return (
      <main className="shell">
        <h1>SiteForge</h1>
        <p className="tagline">The copilot that builds your business website.</p>
        <button className="primary" onClick={() => signInWithPopup(auth, googleProvider)}>
          Sign in with Google
        </button>
      </main>
    );
  }

  return (
    <main className="shell chat-shell">
      <header className="bar">
        <strong>SiteForge</strong>
        <span className="muted">{user.email}</span>
        <button onClick={() => signOut(auth)}>Sign out</button>
      </header>

      <section className="chat">
        {msgs.length === 0 && (
          <p className="muted intro">
            Tell me about your business and I'll build its website — try:
            <em> “I run a bakery in Jaipur and need a site with online enquiries.”</em>
          </p>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>{m.text}</div>
        ))}
        {busy && phase && phase !== "interviewing" && (
          <div className="bubble agent working">{PHASE_LABEL[phase] ?? phase}</div>
        )}
        {snapshot?.phase === "done" && snapshot.pages && (
          <div className="bubble agent">
            <strong>{snapshot.spec?.site_name}</strong> — {snapshot.pages.length} pages
            ({snapshot.pages.join(", ")}), reviewer score {snapshot.score}/10.
          </div>
        )}
        <div ref={bottomRef} />
      </section>

      <footer className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={busy ? "Working…" : "Describe your business…"}
          disabled={busy}
        />
        <button className="primary" onClick={send} disabled={busy || !input.trim()}>
          Send
        </button>
      </footer>
    </main>
  );
}
