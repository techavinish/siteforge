import { useCallback, useEffect, useRef, useState } from "react";
import { onAuthStateChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { marked } from "marked";
import { auth, googleProvider } from "./firebase";
import ConfirmModal from "./ConfirmModal";
import { IconGlobe, IconStop } from "./icons";
import Preview, { type Draft } from "./Preview";
import Sidebar, { type ChatMeta } from "./Sidebar";
import Thinking, { type ThinkBlock } from "./Thinking";

type Msg = {
  role: "user" | "agent";
  text: string;
  thinking?: ThinkBlock[];
  attachment?: "site";
};

const PHASE_LABEL: Record<string, string> = {
  thinking: "Thinking…",
  planning: "Planning your site…",
  writing: "Writing pages…",
  critiquing: "Reviewing quality…",
};

function hashThread(): string | null {
  return location.hash.match(/^#\/c\/(.+)$/)?.[1] ?? null;
}

const STARTER_POOL = [
  { emoji: "🍰", label: "Bakery with custom cakes", prompt: "I run a bakery that specialises in custom wedding cakes and want a website for it." },
  { emoji: "☕", label: "Minimal coffee bar", prompt: "I'm opening a minimalist specialty coffee bar for young professionals and need a website." },
  { emoji: "🧘", label: "Yoga studio", prompt: "I own a yoga studio offering beginner-friendly classes and want a calm, welcoming website." },
  { emoji: "🛠️", label: "Local repair service", prompt: "I run a home appliance repair service and want a website where customers can request a visit." },
  { emoji: "💪", label: "Neighbourhood gym", prompt: "I run a gym with personal training and group classes and want an energetic website." },
  { emoji: "📸", label: "Wedding photographer", prompt: "I'm a wedding photographer and need a portfolio website that gets me bookings." },
  { emoji: "🌸", label: "Flower boutique", prompt: "I own a flower boutique doing bouquets and event decoration, and want an elegant website." },
  { emoji: "🐾", label: "Pet grooming salon", prompt: "I run a pet grooming salon and want a playful website where owners can book appointments." },
  { emoji: "📚", label: "Tutoring academy", prompt: "I run a tutoring academy for school students and want a trustworthy website for parents." },
  { emoji: "🍜", label: "Street-food restaurant", prompt: "I'm opening a street-food restaurant and want a bold website with our menu and story." },
  { emoji: "💇", label: "Hair salon", prompt: "I own a modern hair salon and want a stylish website with services and prices." },
  { emoji: "🏡", label: "Interior designer", prompt: "I'm an interior designer and need a minimal portfolio website that attracts premium clients." },
];

function pickStarters() {
  return [...STARTER_POOL].sort(() => Math.random() - 0.5).slice(0, 4);
}

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
  const [starters, setStarters] = useState(pickStarters);
  const [deleteTarget, setDeleteTarget] = useState<ChatMeta | null>(null);
  const [streamText, setStreamText] = useState("");
  const [thinks, setThinks] = useState<ThinkBlock[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [previewOpen, setPreviewOpen] = useState(true);
  const [previewWide, setPreviewWide] = useState(false);
  const sidebarWasOpen = useRef(false);

  function togglePreviewWide() {
    setPreviewWide((w) => {
      if (!w) {
        // going wide: give the canvas the room — tuck the sidebar away,
        // remembering whether to bring it back on shrink
        sidebarWasOpen.current = !collapsed;
        setCollapsed(true);
      } else if (sidebarWasOpen.current) {
        setCollapsed(false);
      }
      return !w;
    });
  }
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  function toggleSidebar() {
    setCollapsed((c) => {
      localStorage.setItem("sf-side", c ? "0" : "1");
      return !c;
    });
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    await fetch(`/agent/chats/${deleteTarget.thread_id}`, { method: "DELETE" });
    if (user) await loadChats(user);
    if (thread === deleteTarget.thread_id) {
      setThread(null);
      setMsgs([]);
      setDraft(null);
    }
    setDeleteTarget(null);
  }

  async function renameChat(id: string, title: string) {
    await fetch(`/agent/chats/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (user) await loadChats(user);
  }

  const loadChats = useCallback(async (u: User) => {
    const list: ChatMeta[] = await fetch(`/agent/chats?uid=${u.uid}`).then((r) => r.json());
    setChats(list);
    return list;
  }, []);

  const openThread = useCallback(async (id: string) => {
    setThread(id);
    setPhase(null);
    setStreamText("");
    // the thread id lives in the URL: refresh restores it, back/forward
    // moves between conversations — single-route SPA, hash as state
    if (hashThread() !== id) history.pushState(null, "", `#/c/${id}`);
    const [history_, d] = await Promise.all([
      fetch(`/agent/chats/${id}/messages`).then((r) => r.json()),
      fetch(`/agent/draft/${id}`).then((r) => r.json()),
    ]);
    // the site artifact belongs to the message that produced it — on
    // restore, that's the thread's last agent message
    const hasDraft = d?.pages && Object.keys(d.pages).length;
    const msgs_: Msg[] = history_;
    if (hasDraft) {
      for (let i = msgs_.length - 1; i >= 0; i--) {
        if (msgs_[i].role === "agent") {
          msgs_[i] = { ...msgs_[i], attachment: "site" };
          break;
        }
      }
    }
    setMsgs(msgs_);
    setDraft(hasDraft ? d : null);
    setPreviewOpen(Boolean(hasDraft));
    setSuggestions([]);
    setThinks([]);
  }, []);

  useEffect(() => {
    return onAuthStateChanged(auth, async (u) => {
      setUser(u);
      setLoading(false);
      if (u) {
        const list = await loadChats(u);
        const fromUrl = hashThread();
        if (fromUrl && list.some((c) => c.thread_id === fromUrl)) openThread(fromUrl);
        else if (list.length) openThread(list[0].thread_id);
      }
    });
  }, [loadChats, openThread]);

  // browser back/forward between chats
  useEffect(() => {
    const onPop = () => {
      const id = hashThread();
      if (id) openThread(id);
      else {
        setThread(null);
        setMsgs([]);
        setDraft(null);
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [openThread]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, phase, streamText]);

  function newChat() {
    // no API call — the thread is created on the FIRST message, so an
    // abandoned "new chat" never leaves an empty row in the sidebar
    setThread(null);
    setMsgs([]);
    setDraft(null);
    setPhase(null);
    setStarters(pickStarters()); // fresh suggestions every time
    history.pushState(null, "", "#/");
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
      history.pushState(null, "", `#/c/${tid}`);
      loadChats(user); // the row appears in the sidebar NOW, titled later
    }

    const text = raw.trim();
    setInput("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setBusy(true);
    setSuggestions([]);

    // plain variables survive the read loop; state exists only to render
    let acc = "";
    let liveThinks: ThinkBlock[] = [];
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const token = await user.getIdToken();
      const res = await fetch("/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ thread_id: tid, message: text }),
        signal: controller.signal,
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
          if (type === "token") {
            acc += data.text;
            setStreamText(acc);
          } else if (type === "thinking") {
            const last = liveThinks[liveThinks.length - 1];
            if (last && last.node === data.node) last.text += data.text;
            else liveThinks.push({ node: data.node, label: data.label, text: data.text });
            setThinks([...liveThinks]);
          } else if (type === "node") {
            if (data.phase) setPhase(data.phase);
            if (data.node === "respond" && acc) {
              // answer stream finished — promote it, carrying its thinking
              const msg: Msg = {
                role: "agent",
                text: acc,
                thinking: liveThinks.length ? [...liveThinks] : undefined,
              };
              acc = "";
              liveThinks = [];
              setStreamText("");
              setThinks([]);
              setMsgs((m) => [...m, msg]);
            }
            if (data.reply) {
              // deliver: the site artifact is PART of this message
              const msg: Msg = {
                role: "agent",
                text: data.reply,
                thinking: liveThinks.length ? [...liveThinks] : undefined,
                attachment: data.node === "deliver" ? "site" : undefined,
              };
              liveThinks = [];
              setThinks([]);
              setMsgs((m) => [...m, msg]);
            }
          } else if (type === "suggestions") {
            setSuggestions(data.items ?? []);
          } else if (type === "error") {
            setMsgs((m) => [...m, { role: "agent", text: `⚠️ ${data.message}` }]);
          } else if (type === "done" && data.phase === "done") {
            finished = true;
          }
        }
      }
      if (finished && tid) {
        const d = await fetch(`/agent/draft/${tid}`).then((r) => r.json());
        setDraft(d);
        setPreviewOpen(true); // a fresh draft presents itself
      }
      await loadChats(user);
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        // user pressed stop — keep whatever already streamed
        if (acc || liveThinks.length) {
          setMsgs((m) => [
            ...m,
            {
              role: "agent",
              text: acc ? acc + " ⏹" : "⏹ Stopped.",
              thinking: liveThinks.length ? [...liveThinks] : undefined,
            },
          ]);
        }
      } else {
        setMsgs((m) => [
          ...m,
          { role: "agent", text: `⚠️ ${e instanceof Error ? e.message : e} — is the agent running on :8001?` },
        ]);
      }
    } finally {
      abortRef.current = null;
      setStreamText("");
      setThinks([]);
      setBusy(false);
      setPhase(null);
    }
  }

  function stopStream() {
    abortRef.current?.abort();
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

  const showPreview = Boolean(draft) && previewOpen;

  return (
    <div className={showPreview ? (previewWide ? "workspace three wide" : "workspace three") : "workspace two"}>
      <Sidebar
        chats={chats}
        active={thread}
        user={user}
        collapsed={collapsed}
        onToggle={toggleSidebar}
        onSelect={openThread}
        onNew={newChat}
        onDelete={setDeleteTarget}
        onRename={renameChat}
        onSignOut={() => signOut(auth)}
      />

      {deleteTarget && (
        <ConfirmModal
          title="Delete chat?"
          detail={`“${deleteTarget.title}” and its website draft will be permanently deleted.`}
          confirmLabel="Delete"
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      <main className="chat-shell">
        <section className="chat">
          {msgs.length === 0 && (
            <div className="hero-empty">
              <h2>What are we building today?</h2>
              <p className="muted">
                Describe your business — I'll interview you, then design and write your website.
              </p>
              <div className="chips">
                {starters.map((s) => (
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
              <div key={i} className="agent-turn">
                {m.thinking && <Thinking blocks={m.thinking} />}
                <div
                  className="agent-md"
                  dangerouslySetInnerHTML={{ __html: marked.parse(m.text, { async: false }) as string }}
                />
                {m.attachment === "site" && draft && (
                  <button className="site-card" onClick={() => setPreviewOpen((o) => !o)}>
                    <span className="site-card-ico"><IconGlobe /></span>
                    <span className="site-card-body">
                      <strong>{draft.spec?.site_name ?? "Your website"}</strong>
                      <span className="muted">
                        {Object.keys(draft.pages ?? {}).length} pages · {previewOpen ? "hide" : "view"} website
                      </span>
                    </span>
                  </button>
                )}
              </div>
            ),
          )}
          {thinks.length > 0 && <Thinking blocks={thinks} streaming={!streamText} />}
          {streamText && (
            <div
              className="agent-md streaming"
              dangerouslySetInnerHTML={{ __html: marked.parse(streamText, { async: false }) as string }}
            />
          )}
          {busy && !streamText && thinks.length === 0 && (
            <div className="working-row">
              <span className="dots"><i /><i /><i /></span>
              {phase && PHASE_LABEL[phase] && <span className="phase-tag">{PHASE_LABEL[phase]}</span>}
            </div>
          )}
          <div ref={bottomRef} />
        </section>

        {suggestions.length > 0 && !busy && (
          <div className="suggest-row">
            {suggestions.map((s) => (
              <button key={s} className="chip sm" onClick={() => send(s)}>{s}</button>
            ))}
          </div>
        )}

        <footer className="composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder={busy ? "Working…" : "Describe your business…"}
            disabled={busy}
          />
          {busy ? (
            <button className="stop" onClick={stopStream} data-tip="Stop generating">
              <IconStop />
            </button>
          ) : (
            <button className="primary" onClick={() => send()} disabled={!input.trim()}>
              Send
            </button>
          )}
        </footer>
      </main>

      {showPreview && draft && thread && (
        <Preview
          draft={draft}
          threadId={thread}
          wide={previewWide}
          onToggleWide={togglePreviewWide}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </div>
  );
}
