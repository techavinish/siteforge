import type { User } from "firebase/auth";

export type ChatMeta = { thread_id: string; title: string; updated_at: string };

export default function Sidebar({
  chats,
  active,
  user,
  onSelect,
  onNew,
  onSignOut,
}: {
  chats: ChatMeta[];
  active: string | null;
  user: User;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSignOut: () => void;
}) {
  return (
    <nav className="sidebar">
      <div className="side-head">
        <span className="logo">SiteForge</span>
      </div>

      <button className="new-chat" onClick={onNew}>+ New chat</button>

      <div className="chat-list">
        {chats.map((c) => (
          <button
            key={c.thread_id}
            className={c.thread_id === active ? "chat-item active" : "chat-item"}
            onClick={() => onSelect(c.thread_id)}
            title={c.title}
          >
            {c.title}
          </button>
        ))}
        {chats.length === 0 && <p className="muted side-empty">No chats yet</p>}
      </div>

      <div className="side-foot">
        {user.photoURL && <img className="avatar sm" src={user.photoURL} alt="" />}
        <span className="muted foot-mail">{user.email}</span>
        <button className="ghost" onClick={onSignOut} title="Sign out">↩</button>
      </div>
    </nav>
  );
}
