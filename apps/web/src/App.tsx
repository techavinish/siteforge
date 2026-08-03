import { useCallback, useEffect, useRef, useState } from "react";
import { onAuthStateChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { marked } from "marked";
import { auth, googleProvider } from "./firebase";
import Preview, { type Draft } from "./Preview";
import Sidebar, { type ChatMeta } from "./Sidebar";

type Msg = { role: "user" | "agent"; text: string };

const PHASE_LABEL: Record<string, string> = {
  planning: "Planning your site…",
  writing: "Writing pages…",
  critiquing: "Reviewing quality…",
};

const STARTERS = [
  {
    emoji: "🍰",
    label: "Bakery with custom cakes",
    prompt: "I run a bakery that specialises in custom wedding cakes and want a website for it.",
  },
  {
    emoji: "☕",
    label: "Minimal coffee bar",
    prompt: "I'm opening a minimalist specialty coffee bar for young professionals and need a website.",
  },
  {
    emoji: "🧘",
    label: "Yoga studio",
    prompt: "I own a yoga studio offering beginner-friendly classes and want a calm, welcoming website.",
  },
  {
    emoji: "🛠️",
    label: "Local repair service",
    prompt: "I run a home appliance repair service and want a website where customers can request a visit.",
  },
];

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [chats, setChats] = useState<ChatMeta[]>([]);
  const [thread, setThread] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sf-side") === "1");
  const bottomRef = useRef<HTMLDivElement>(null);

  function toggleSidebar() {
    setCollapsed((c) => {
      localStorage.setItem("sf-side", c ? "0" : "1");
      return !c;
    });
  }

  async function deleteChat(id: string) {
    if (!window.confirm("Delete this chat and its draft?")) return;
    await fetch(`/agent/chats/${id}`, { method: "DELETE" });
    if (user) await loadChats(user);
    if (thread === id) {
      setThread(null);
      setMsgs([]);
      setDraft(null);
    }
  }

  const loadChats = useCallback(async (u: User) => {
    const list: ChatMeta[] = await fetch(`/agent/chats?uid=${u.uid}`).then((r) => r.json());
    setChats(list);
    return list;
  }, []);

  const openThread = useCallback(async (id: string) => {
    setThread(id);
    setPhase(null);
    const [history, d] = await Promise.all([
      fetch(`/agent/chats/${id}/messages`).then((r) => r.json()),
      fetch(`/agent/draft/${id}`).then((r) => r.json()),
    ]);
    setMsgs(history);
    setDraft(d?.pages && Object.keys(d.pages).length ? d : null);
  }, []);

  useEffect(() => {
    return onAuthStateChanged(auth, async (u) => {
      setUser(u);
      setLoading(false);
      if (u) {
        const list = await loadChats(u);
        if (list.length) openThread(list[0].thread_id);
      }
    });
  }, [loadChats, openThread]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, phase]);

  function newChat() {
    // no API call — the thread is created on the FIRST message, so an
    // abandoned "new chat" never leaves an empty row in the sidebar
    setThread(null);
    setMsgs([]);
    setDraft(null);
    setPhase(null);
  }

  async function send(textOverride?: string) {
    const raw = textOverride ?? input;
    if (!user || !raw.trim() || busy) return;
    let tid = thread;
    if (!tid) {
      const created = await fetch("/agent/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid: user.uid }),
      }).then((r) => r.json());
      tid = created.thread_id;
      setThread(tid);
    }

    const text = raw.trim();
    setInput("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);

    try {
      const token = await user.getIdToken();
      const res = await fetch("/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ thread_id: tid, message: text }),
      });
      if (!res.ok || !res.body) throw new Error(`agent said ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;
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
          } else if (type === "done" && data.phase === "done") {
            finished = true;
          }
        }
      }
      if (finished && tid) {
        const d = await fetch(`/agent/draft/${tid}`).then((r) => r.json());
        setDraft(d);
      }
      await loadChats(user);
    } catch (e) {
      setMsgs((m) => [
        ...m,
        { role: "agent", text: `⚠️ ${e instanceof Error ? e.message : e} — is the agent running on :8001?` },
      ]);
    } finally {
      setBusy(false);
      setPhase(null);
    }
  }

  if (loading) {
    return (
      <div className="boot">
        <span className="spinner lg" />
      </div>
    );
  }

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
    <div className={draft ? "workspace three" : "workspace two"}>
      <Sidebar
        chats={chats}
        active={thread}
        user={user}
        collapsed={collapsed}
        onToggle={toggleSidebar}
        onSelect={openThread}
        onNew={newChat}
        onDelete={deleteChat}
        onSignOut={() => signOut(auth)}
      />

      <main className="chat-shell">
        <section className="chat">
          {msgs.length === 0 && (
            <div className="hero-empty">
              <h2>What are we building today?</h2>
              <p className="muted">
                Describe your business — I'll interview you, then design and write your website.
              </p>
              <div className="chips">
                {STARTERS.map((s) => (
                  <button key={s.label} className="chip" onClick={() => send(s.prompt)}>
                    <span className="chip-emoji">{s.emoji}</span>
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
          )}
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="bubble user">{m.text}</div>
            ) : (
              <div
                key={i}
                className="agent-md"
                dangerouslySetInnerHTML={{ __html: marked.parse(m.text, { async: false }) as string }}
              />
            ),
          )}
          {busy && (
            <div className="working-row">
              <span className="dots"><i /><i /><i /></span>
              {phase && PHASE_LABEL[phase] && <span className="phase-tag">{PHASE_LABEL[phase]}</span>}
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
          <button className="primary" onClick={() => send()} disabled={busy || !input.trim()}>
            Send
          </button>
        </footer>
      </main>

      {draft && <Preview draft={draft} />}
    </div>
  );
}
