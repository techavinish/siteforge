import { useCallback, useEffect, useRef, useState } from "react";
import { onAuthStateChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import {
  Cake, Camera, Coffee, Dumbbell, Flower, Flower2, GraduationCap,
  PawPrint, Scissors, Sofa, UtensilsCrossed, Wrench,
} from "lucide-react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { auth, googleProvider } from "./firebase";
import { authFetch, idToken, setAuthUser } from "./api";
import ConfirmModal from "./ConfirmModal";
import { IconArrowUp, IconChevronDown, IconClip, IconCopy, IconGlobe, IconRetry, IconStop, IconX } from "./icons";
import Preview, { type Draft } from "./Preview";
import Sidebar, { type ChatMeta } from "./Sidebar";
import Thinking, { type ThinkBlock } from "./Thinking";

type Msg = {
  role: "user" | "agent";
  text: string;
  thinking?: ThinkBlock[];
  attachment?: "site";
  error?: boolean; // failed turn — rendered as a card with retry
};

/** All agent markdown flows through here: parsed once, sanitized always.
 *  marked passes raw HTML straight through — never trust model output
 *  (or rehydrated history) inside the app origin. */
function md(text: string): string {
  return DOMPurify.sanitize(marked.parse(text, { async: false }) as string);
}

const PHASE_LABEL: Record<string, string> = {
  thinking: "Thinking…",
  planning: "Planning your site…",
  illustrating: "Finding photos…",
  writing: "Writing pages…",
  critiquing: "Reviewing quality…",
};

function hashThread(): string | null {
  return location.hash.match(/^#\/c\/(.+)$/)?.[1] ?? null;
}


const STARTER_POOL = [
  { icon: Cake, label: "Bakery with custom cakes", prompt: "I run a bakery that specialises in custom wedding cakes and want a website for it." },
  { icon: Coffee, label: "Minimal coffee bar", prompt: "I'm opening a minimalist specialty coffee bar for young professionals and need a website." },
  { icon: Flower2, label: "Yoga studio", prompt: "I own a yoga studio offering beginner-friendly classes and want a calm, welcoming website." },
  { icon: Wrench, label: "Local repair service", prompt: "I run a home appliance repair service and want a website where customers can request a visit." },
  { icon: Dumbbell, label: "Neighbourhood gym", prompt: "I run a gym with personal training and group classes and want an energetic website." },
  { icon: Camera, label: "Wedding photographer", prompt: "I'm a wedding photographer and need a portfolio website that gets me bookings." },
  { icon: Flower, label: "Flower boutique", prompt: "I own a flower boutique doing bouquets and event decoration, and want an elegant website." },
  { icon: PawPrint, label: "Pet grooming salon", prompt: "I run a pet grooming salon and want a playful website where owners can book appointments." },
  { icon: GraduationCap, label: "Tutoring academy", prompt: "I run a tutoring academy for school students and want a trustworthy website for parents." },
  { icon: UtensilsCrossed, label: "Street-food restaurant", prompt: "I'm opening a street-food restaurant and want a bold website with our menu and story." },
  { icon: Scissors, label: "Hair salon", prompt: "I own a modern hair salon and want a stylish website with services and prices." },
  { icon: Sofa, label: "Interior designer", prompt: "I'm an interior designer and need a minimal portfolio website that attracts premium clients." },
];

function pickStarters() {
  return [...STARTER_POOL].sort(() => Math.random() - 0.5).slice(0, 4);
}

// the welcome headline cycles through what SiteForge can build —
// every phrase ends in "website" so it always reads as a full sentence
const BUILD_WORDS = [
  "a coffee bar website",
  "a bakery website",
  "a yoga studio website",
  "a gym website",
  "a portfolio website",
  "a restaurant website",
  "a salon website",
  "your business website",
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
  const [starters, setStarters] = useState(pickStarters);
  const [deleteTarget, setDeleteTarget] = useState<ChatMeta | null>(null);
  const [streamText, setStreamText] = useState("");
  const [thinks, setThinks] = useState<ThinkBlock[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [previewOpen, setPreviewOpen] = useState(true);
  const [previewWide, setPreviewWide] = useState(false);
  const sidebarWasOpen = useRef(false);

  // an open artifact deserves the room: tuck the sidebar away while the
  // website canvas is visible, bring it back when the canvas closes
  useEffect(() => {
    if (draft && previewOpen) {
      sidebarWasOpen.current = !collapsed || sidebarWasOpen.current;
      setCollapsed(true);
    } else if (sidebarWasOpen.current) {
      sidebarWasOpen.current = false;
      setCollapsed(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, previewOpen]);

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
  const activeThread = useRef<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  // the owner's logo, staged in the composer until the message sends
  const [pendingLogo, setPendingLogo] = useState<{ name: string; dataUrl: string } | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [positioning, setPositioning] = useState(false);
  const [wordIdx, setWordIdx] = useState(0);
  const [typed, setTyped] = useState("");
  const [erasing, setErasing] = useState(false);

  // typewriter: type the word character by character, hold, erase, next —
  // width grows/shrinks naturally with the characters, no layout jump
  const onWelcome = msgs.length === 0 && !busy;
  useEffect(() => {
    if (!onWelcome) return;
    const word = BUILD_WORDS[wordIdx];
    let delay: number;
    let step: () => void;
    if (!erasing && typed === word) {
      delay = 1600; // let the finished word breathe
      step = () => setErasing(true);
    } else if (erasing && typed === "") {
      delay = 250;
      step = () => {
        setErasing(false);
        setWordIdx((i) => (i + 1) % BUILD_WORDS.length);
      };
    } else if (erasing) {
      delay = 35;
      step = () => setTyped(word.slice(0, typed.length - 1));
    } else {
      delay = 70;
      step = () => setTyped(word.slice(0, typed.length + 1));
    }
    const t = setTimeout(step, delay);
    return () => clearTimeout(t);
  }, [onWelcome, typed, erasing, wordIdx]);

  function onChatScroll() {
    const el = chatRef.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
    if (el.scrollTop < 60) loadOlderMessages();
  }

  function scrollToBottom() {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  function toggleSidebar() {
    setCollapsed((c) => {
      localStorage.setItem("sf-side", c ? "0" : "1");
      return !c;
    });
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    await authFetch(`/agent/chats/${deleteTarget.thread_id}`, { method: "DELETE" });
    if (user) await loadChats(user);
    if (thread === deleteTarget.thread_id) {
      setThread(null);
      setMsgs([]);
      setDraft(null);
      history.pushState(null, "", "#/");
    }
    setDeleteTarget(null);
  }

  async function renameChat(id: string, title: string) {
    await authFetch(`/agent/chats/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (user) await loadChats(user);
  }

  const searchRef = useRef("");
  const [chatsCursor, setChatsCursor] = useState<string | null>(null);
  const [msgsCursor, setMsgsCursor] = useState<string | null>(null);
  const loadingOlder = useRef(false);

  const loadChats = useCallback(
    async (u: User, opts: { q?: string; cursor?: string; append?: boolean } = {}) => {
      const params = new URLSearchParams(); // identity comes from the token
      const q = opts.q ?? searchRef.current;
      if (q) params.set("q", q);
      if (opts.cursor) params.set("cursor", opts.cursor);
      const { items, next_cursor } = await authFetch(`/agent/chats?${params}`).then((r) => r.json());
      setChats((prev) => (opts.append ? [...prev, ...items] : items));
      setChatsCursor(next_cursor);
      return items as ChatMeta[];
    },
    [],
  );

  const openThread = useCallback(async (id: string) => {
    activeThread.current = id;
    abortRef.current?.abort(); // navigating away stops the visible stream
    setThread(id);
    setPhase(null);
    setStreamText("");
    setAtBottom(true);
    setPositioning(true); // hide the list until it's anchored at the bottom
    // the thread id lives in the URL: refresh restores it, back/forward
    // moves between conversations — single-route SPA, hash as state
    if (hashThread() !== id) history.pushState(null, "", `#/c/${id}`);
    const [page, d] = await Promise.all([
      authFetch(`/agent/chats/${id}/messages`).then((r) => r.json()),
      authFetch(`/agent/draft/${id}`).then((r) => r.json()),
    ]);
    // the site artifact belongs to the message that produced it — on
    // restore, that's the thread's last agent message (older schema rows)
    if (activeThread.current !== id) return; // user already moved on
    const hasDraft = d?.pages && Object.keys(d.pages).length;
    const msgs_: Msg[] = page.items;
    if (hasDraft && !msgs_.some((m) => m.attachment === "site")) {
      for (let i = msgs_.length - 1; i >= 0; i--) {
        if (msgs_[i].role === "agent") {
          msgs_[i] = { ...msgs_[i], attachment: "site" };
          break;
        }
      }
    }
    setMsgs(msgs_);
    setMsgsCursor(page.next_cursor);
    setDraft(hasDraft ? d : null);
    setPreviewOpen(Boolean(hasDraft));
    setSuggestions([]);
    setThinks([]);
    // anchor at the latest message BEFORE revealing — the user never sees
    // the list scroll; it simply opens at the bottom (double rAF waits for
    // layout of the freshly rendered messages)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = chatRef.current;
        if (el) el.scrollTop = el.scrollHeight;
        setAtBottom(true);
        setPositioning(false);
      });
    });
  }, []);

  // reaching the top of the chat loads the previous page of history,
  // keeping the viewport anchored on what the user was reading
  async function loadOlderMessages() {
    const el = chatRef.current;
    if (!el || !thread || !msgsCursor || loadingOlder.current) return;
    loadingOlder.current = true;
    try {
      const page = await authFetch(
        `/agent/chats/${thread}/messages?cursor=${msgsCursor}`,
      ).then((r) => (r.ok ? r.json() : { items: [], next_cursor: msgsCursor }));
      const prevHeight = el.scrollHeight;
      setMsgs((m) => [...page.items, ...m]);
      setMsgsCursor(page.next_cursor);
      requestAnimationFrame(() => {
        el.scrollTop += el.scrollHeight - prevHeight;
      });
    } finally {
      loadingOlder.current = false;
    }
  }

  useEffect(() => {
    return onAuthStateChanged(auth, async (u) => {
      setAuthUser(u);
      setUser(u);
      setLoading(false);
      if (u) {
        const list = await loadChats(u);
        const fromUrl = hashThread();
        // deep link restores its chat; otherwise ALWAYS start on the
        // welcome screen — never dump the user into an old conversation
        if (fromUrl && list.some((c) => c.thread_id === fromUrl)) openThread(fromUrl);
      }
    });
  }, [loadChats, openThread]);

  // keyboard shortcuts: Cmd/Ctrl+Shift+O new chat, Cmd/Ctrl+K search
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.shiftKey && e.key.toLowerCase() === "o") {
        e.preventDefault();
        newChat();
      } else if (mod && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCollapsed(false);
        window.dispatchEvent(new Event("sf-focus-search"));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // follow the stream only while the user is at the bottom — scrolling up
  // to read pauses auto-scroll; the ↓ button jumps back into the flow
  useEffect(() => {
    if (atBottom) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, phase, streamText, thinks, atBottom]);

  function newChat() {
    // no API call — the thread is created on the FIRST message, so an
    // abandoned "new chat" never leaves an empty row in the sidebar
    activeThread.current = null;
    abortRef.current?.abort();
    setMsgsCursor(null);
    setThread(null);
    setMsgs([]);
    setDraft(null);
    setPhase(null);
    setAtBottom(true);
    setSuggestions([]);
    setStarters(pickStarters()); // fresh suggestions every time
    history.pushState(null, "", "#/");
  }

  function pickLogo(file: File | undefined | null) {
    if (!file) return;
    if (!/^image\/(png|jpeg|svg\+xml|webp)$/.test(file.type)) return;
    if (file.size > 512 * 1024) {
      setMsgs((m) => [...m, { role: "agent", text: "That logo is over 512 KB — please use a smaller file.", error: true }]);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setPendingLogo({ name: file.name, dataUrl: String(reader.result) });
    reader.readAsDataURL(file);
  }

  async function send(textOverride?: string) {
    const raw = textOverride ?? input;
    if (!user || !(raw.trim() || pendingLogo) || busy) return;
    let tid = thread;
    if (!tid) {
      const created = await authFetch("/agent/chats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid: user.uid }),
      }).then((r) => r.json());
      tid = created.thread_id;
      activeThread.current = tid;
      setThread(tid);
      history.pushState(null, "", `#/c/${tid}`);
      loadChats(user); // the row appears in the sidebar NOW, titled later
    }

    // a logo can ride along with (or without) words — the agent is told
    // in plain language so the brief picks it up naturally. Cleared only
    // after the upload SUCCEEDS: a failed send must not eat the file.
    const logo = pendingLogo;
    const text = raw.trim() || "I've uploaded our logo — please use it on the site.";
    const myTid = tid; // everything below is scoped to THIS thread
    setInput("");
    if (composerRef.current) composerRef.current.style.height = "auto";
    setMsgs((m) => [...m, { role: "user", text }]);
    setAtBottom(true);
    requestAnimationFrame(scrollToBottom); // your own message never lands off-screen
    setBusy(true);
    setSuggestions([]);
    const onThread = () => activeThread.current === myTid || activeThread.current === null && myTid === thread;

    // plain variables survive the read loop; state exists only to render
    let acc = "";
    let liveThinks: ThinkBlock[] = [];
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      if (logo) {
        const up = await authFetch(`/agent/logo/${myTid}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data_url: logo.dataUrl }),
        });
        if (!up.ok) {
          const j = await up.json().catch(() => ({ detail: "logo upload failed" }));
          throw new Error(j.detail ?? "logo upload failed");
        }
        setPendingLogo(null);
      }
      const token = await user.getIdToken();
      const res = await authFetch("/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ thread_id: tid, message: text }),
        signal: controller.signal,
      });
      if (!res.ok) {
        // surface the BE's own words (rate limits, ownership) — not a code
        let msg = `agent said ${res.status}`;
        try {
          const j = await res.json();
          if (j.detail) msg = j.detail;
        } catch { /* body wasn't json */ }
        throw new Error(msg);
      }
      if (!res.body) throw new Error("agent returned no stream");

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
          const pushAgent = (msg: Msg) =>
            setMsgs((m) =>
              m.length && m[m.length - 1].role === "agent" && m[m.length - 1].text === msg.text
                ? m // guard: never render the same agent message twice in a row
                : [...m, msg],
            );
          if (!onThread()) continue; // user navigated away — drop late events
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
              pushAgent(msg);
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
              pushAgent(msg);
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
      if (finished && tid && onThread()) {
        const d = await authFetch(`/agent/draft/${tid}`).then((r) => r.json());
        if (onThread()) {
          setDraft(d);
          setPreviewOpen(true); // a fresh draft presents itself
        }
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
      } else if (onThread()) {
        const msg = e instanceof Error ? e.message : String(e);
        setMsgs((m) => [...m, { role: "agent", text: msg, error: true }]);
      }
    } finally {
      abortRef.current = null;
      setStreamText("");
      setThinks([]);
      setBusy(false);
      setPhase(null);
      composerRef.current?.focus();
    }
  }

  // last user message — powers retry after an error and regenerate
  function lastUserText(): string {
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i].role === "user") return msgs[i].text;
    }
    return "";
  }

  function retryLast() {
    const text = lastUserText();
    if (!text) return;
    // drop the trailing error/agent turn, resend the same user message
    setMsgs((m) => {
      const copy = [...m];
      while (copy.length && copy[copy.length - 1].role === "agent") copy.pop();
      if (copy.length && copy[copy.length - 1].role === "user") copy.pop();
      return copy;
    });
    send(text);
  }

  async function copyText(text: string, e: React.MouseEvent<HTMLButtonElement>) {
    await navigator.clipboard.writeText(text);
    const btn = e.currentTarget;
    btn.classList.add("copied");
    setTimeout(() => btn.classList.remove("copied"), 1400);
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
      <main className="landing">
        <div className="landing-card">
          <span className="landing-logo">S</span>
          <h1>SiteForge</h1>
          <p className="landing-type">
            Let's build <span className="type-word">{typed}</span>
            <span className="type-caret" />
          </p>
          <p className="muted landing-sub">
            Chat for a minute. Get a designed, written, photographed website —
            live on the internet.
          </p>
          <button className="primary landing-cta" onClick={() => signInWithPopup(auth, googleProvider)}>
            Continue with Google
          </button>
        </div>
      </main>
    );
  }

  const showPreview = Boolean(draft) && previewOpen;

  // one composer, two homes: centered in the welcome stage before the
  // first message, docked at the bottom once a conversation exists
  const composerEl = (
    <footer className="composer">
      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/svg+xml,image/webp"
        hidden
        onChange={(e) => {
          pickLogo(e.target.files?.[0]);
          e.target.value = ""; // same file re-picked still fires change
        }}
      />
      <button
        className="icon-btn clip"
        aria-label="Attach your logo"
        data-tip="Attach your logo"
        onClick={() => fileRef.current?.click()}
      >
        <IconClip />
      </button>
      {pendingLogo && (
        <span className="attach-chip">
          <img src={pendingLogo.dataUrl} alt="" />
          {pendingLogo.name}
          <button aria-label="Remove logo" onClick={() => setPendingLogo(null)}><IconX /></button>
        </span>
      )}
      <textarea
        ref={composerRef}
        rows={1}
        autoFocus
        value={input}
        onChange={(e) => {
          setInput(e.target.value);
          e.target.style.height = "auto";
          e.target.style.height = Math.min(e.target.scrollHeight, 200) + "px";
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (!busy) send();
          }
          if (e.key === "Escape" && busy) stopStream();
        }}
        placeholder={busy ? "Streaming… (Esc to stop)" : "Describe your business…"}
        aria-label="Message SiteForge"
      />
      {busy ? (
        <button className="round-action stop" onClick={stopStream} aria-label="Stop generating" data-tip="Stop generating">
          <IconStop />
        </button>
      ) : (
        <button
          className="round-action send"
          onClick={() => send()}
          disabled={!input.trim() && !pendingLogo}
          aria-label="Send message"
        >
          <IconArrowUp />
        </button>
      )}
    </footer>
  );

  return (
    <div className={showPreview ? (previewWide ? "workspace three wide" : "workspace three") : "workspace two"}>
      <Sidebar
        chats={chats}
        hasMore={Boolean(chatsCursor)}
        active={thread}
        user={user}
        collapsed={collapsed}
        onToggle={toggleSidebar}
        onSelect={(id) => {
          openThread(id);
          if (window.matchMedia("(max-width: 640px)").matches) setCollapsed(true);
        }}
        onNew={newChat}
        onDelete={setDeleteTarget}
        onRename={renameChat}
        onSearch={(q) => {
          searchRef.current = q;
          if (user) loadChats(user, { q });
        }}
        onLoadMore={() => user && chatsCursor && loadChats(user, { cursor: chatsCursor, append: true })}
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
        {onWelcome ? (
          // the welcome moment: headline, composer, and starters as ONE
          // centered group — nothing docked, no header over an empty page
          <div className="welcome-stage">
            <div className="hero-empty">
              <h2>
                Let's build <span className="type-word">{typed}</span>
                <span className="type-caret" />
              </h2>
              <p className="muted">
                One sentence about your business — I'll design it, write it,
                and put it live. In minutes.
              </p>
            </div>
            {composerEl}
            <div className="chips">
              {starters.map((s) => (
                <button key={s.label} className="chip" onClick={() => send(s.prompt)}>
                  <span className="chip-ico"><s.icon size={14} strokeWidth={1.9} /></span>
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
        <>
        <div className="chat-top" title={chats.find((c) => c.thread_id === thread)?.title}>
          {thread ? chats.find((c) => c.thread_id === thread)?.title ?? "…" : "New chat"}
        </div>
        <section
          className={positioning ? "chat positioning" : "chat"}
          ref={chatRef}
          onScroll={onChatScroll}
        >
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="bubble user">{m.text}</div>
            ) : m.error ? (
              <div key={i} className="msg-error" role="alert">
                <span>{m.text}</span>
                <button className="retry-btn" onClick={retryLast}>Retry</button>
              </div>
            ) : (
              <div key={i} className="agent-turn">
                {m.thinking && <Thinking blocks={m.thinking} />}
                <div
                  className="agent-md"
                  dangerouslySetInnerHTML={{ __html: md(m.text) }}
                />
                <div className="msg-actions">
                  <button
                    className="icon-btn"
                    aria-label="Copy message"
                    data-tip="Copy"
                    onClick={(e) => copyText(m.text, e)}
                  >
                    <IconCopy />
                  </button>
                  {i === msgs.length - 1 && !busy && (
                    <button
                      className="icon-btn"
                      aria-label="Regenerate response"
                      data-tip="Regenerate"
                      onClick={retryLast}
                    >
                      <IconRetry />
                    </button>
                  )}
                </div>
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
              dangerouslySetInnerHTML={{ __html: md(streamText) }}
            />
          )}
          {busy && !streamText && thinks.length === 0 && (
            <div className="working-row" role="status" aria-live="polite">
              <span className="shimmer">
                {(phase && PHASE_LABEL[phase]) || "Thinking…"}
              </span>
            </div>
          )}
          <div ref={bottomRef} />
        </section>

        {!atBottom && msgs.length > 0 && (
          <button className="jump-down" onClick={scrollToBottom} aria-label="Jump to latest">
            <IconChevronDown />
          </button>
        )}

        {suggestions.length > 0 && !busy && (
          <div className="suggest-row">
            {suggestions.map((s) => (
              <button key={s} className="chip sm" onClick={() => send(s)}>{s}</button>
            ))}
          </div>
        )}

        {composerEl}
        </>
        )}
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
