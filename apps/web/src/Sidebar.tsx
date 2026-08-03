import { useMemo, useState } from "react";
import type { User } from "firebase/auth";

export type ChatMeta = { thread_id: string; title: string; updated_at: string };

export default function Sidebar({
  chats,
  active,
  user,
  collapsed,
  onToggle,
  onSelect,
  onNew,
  onDelete,
  onSignOut,
}: {
  chats: ChatMeta[];
  active: string | null;
  user: User;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onSignOut: () => void;
}) {
  const [q, setQ] = useState("");
  const filtered = useMemo(
    () => chats.filter((c) => c.title.toLowerCase().includes(q.trim().toLowerCase())),
    [chats, q],
  );

  if (collapsed) {
    return (
      <nav className="sidebar collapsed">
        <button className="icon-btn" onClick={onToggle} title="Open sidebar">☰</button>
        <button className="icon-btn accent" onClick={onNew} title="New chat">+</button>
      </nav>
    );
  }

  return (
    <nav className="sidebar">
      <div className="side-head">
        <span className="logo">SiteForge</span>
        <button className="icon-btn" onClick={onToggle} title="Collapse sidebar">⟨</button>
      </div>

      <button className="new-chat" onClick={onNew}>+ New chat</button>

      <div className="side-search">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search chats…"
        />
      </div>

      <div className="chat-list">
        {filtered.map((c) => (
          <div key={c.thread_id} className={c.thread_id === active ? "chat-row active" : "chat-row"}>
            <button className="chat-item" onClick={() => onSelect(c.thread_id)} title={c.title}>
              {c.title}
            </button>
            <button
              className="chat-del"
              title="Delete chat"
              onClick={(e) => {
                e.stopPropagation();
                onDelete(c.thread_id);
              }}
            >
              ×
            </button>
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="muted side-empty">{q ? "No matches" : "No chats yet"}</p>
        )}
      </div>

      <div className="side-foot">
        {user.photoURL && <img className="avatar sm" src={user.photoURL} alt="" />}
        <span className="muted foot-mail">{user.email}</span>
        <button className="ghost" onClick={onSignOut} title="Sign out">↩</button>
      </div>
    </nav>
  );
}
