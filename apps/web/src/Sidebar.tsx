import { useMemo, useState } from "react";
import type { User } from "firebase/auth";
import { IconLogout, IconPanel, IconPencil, IconPlus, IconSearch, IconX } from "./icons";

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
  onRename,
  onSignOut,
}: {
  chats: ChatMeta[];
  active: string | null;
  user: User;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (chat: ChatMeta) => void;
  onRename: (id: string, title: string) => Promise<void>;
  onSignOut: () => void;
}) {
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const filtered = useMemo(
    () => chats.filter((c) => c.title.toLowerCase().includes(q.trim().toLowerCase())),
    [chats, q],
  );

  function startEdit(c: ChatMeta) {
    setEditing(c.thread_id);
    setEditValue(c.title);
  }

  async function commitEdit() {
    if (editing && editValue.trim()) await onRename(editing, editValue.trim());
    setEditing(null);
  }

  if (collapsed) {
    return (
      <nav className="sidebar collapsed">
        <button className="icon-btn" onClick={onToggle} title="Open sidebar">
          <IconPanel />
        </button>
        <button className="icon-btn accent" onClick={onNew} title="New chat">
          <IconPlus />
        </button>
      </nav>
    );
  }

  return (
    <nav className="sidebar">
      <div className="side-head">
        <span className="logo">SiteForge</span>
        <button className="icon-btn" onClick={onToggle} title="Collapse sidebar">
          <IconPanel />
        </button>
      </div>

      <button className="new-chat" onClick={onNew}>
        <IconPlus />
        <span>New chat</span>
      </button>

      <div className="side-search">
        <span className="search-ico"><IconSearch /></span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search chats" />
      </div>

      <div className="chat-list">
        {filtered.map((c) => (
          <div key={c.thread_id} className={c.thread_id === active ? "chat-row active" : "chat-row"}>
            {editing === c.thread_id ? (
              <input
                className="chat-rename"
                value={editValue}
                autoFocus
                onChange={(e) => setEditValue(e.target.value)}
                onBlur={commitEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitEdit();
                  if (e.key === "Escape") setEditing(null);
                }}
              />
            ) : (
              <>
                <button
                  className="chat-item"
                  onClick={() => onSelect(c.thread_id)}
                  onDoubleClick={() => startEdit(c)}
                  title={c.title}
                >
                  {c.title}
                </button>
                <button
                  className="icon-btn row-action"
                  title="Rename"
                  onClick={(e) => {
                    e.stopPropagation();
                    startEdit(c);
                  }}
                >
                  <IconPencil />
                </button>
                <button
                  className="icon-btn row-action del"
                  title="Delete chat"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(c);
                  }}
                >
                  <IconX />
                </button>
              </>
            )}
          </div>
        ))}
        {filtered.length === 0 && (
          <p className="muted side-empty">{q ? "No matches" : "No chats yet"}</p>
        )}
      </div>

      <div className="side-foot">
        {user.photoURL && <img className="avatar sm" src={user.photoURL} alt="" />}
        <span className="muted foot-mail">{user.email}</span>
        <button className="icon-btn" onClick={onSignOut} title="Sign out">
          <IconLogout />
        </button>
      </div>
    </nav>
  );
}
