import { useCallback, useEffect, useState } from "react";
import { authFetch } from "./api";
import { IconInbox, IconRefresh } from "./icons";

export type Booking = {
  id: number;
  name: string;
  contact: string;
  service: string | null;
  message: string | null;
  status: "new" | "contacted" | "closed";
  created_at: string;
};

type Counts = { new: number; contacted: number; closed: number };

/** "2m ago" / "3h ago" / "12 Aug" — bookings are triage, recency is the
 *  first thing an owner scans for. */
function ago(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

// each status knows its one next action — no dropdowns to fiddle with
const NEXT: Record<Booking["status"], { to: Booking["status"]; label: string } | null> = {
  new: { to: "contacted", label: "Mark contacted" },
  contacted: { to: "closed", label: "Close" },
  closed: { to: "new", label: "Reopen" },
};

/** The client's booking inbox — every submission from their published
 *  site's booking form, newest first, triaged with one tap. */
export default function Bookings({ threadId, onCounts }: {
  threadId: string;
  onCounts?: (c: Counts) => void;
}) {
  const [items, setItems] = useState<Booking[]>([]);
  const [counts, setCounts] = useState<Counts>({ new: 0, contacted: 0, closed: 0 });
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (append = false, cur?: string | null) => {
    setLoading(true);
    try {
      const params = cur ? `?cursor=${cur}` : "";
      const r = await authFetch(`/agent/bookings/${threadId}${params}`);
      if (!r.ok) return;
      const data = await r.json();
      setItems((prev) => (append ? [...prev, ...data.items] : data.items));
      setCounts(data.counts);
      setCursor(data.next_cursor);
      onCounts?.(data.counts);
    } finally {
      setLoading(false);
    }
  }, [threadId, onCounts]);

  useEffect(() => { load(); }, [load]);

  async function advance(b: Booking) {
    const next = NEXT[b.status];
    if (!next) return;
    // optimistic: the row updates under the finger, the server follows
    setItems((list) => list.map((x) => (x.id === b.id ? { ...x, status: next.to } : x)));
    setCounts((c) => ({
      ...c,
      [b.status]: Math.max(0, c[b.status] - 1),
      [next.to]: c[next.to] + 1,
    }));
    const r = await authFetch(`/agent/bookings/${threadId}/${b.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next.to }),
    });
    if (!r.ok) load(); // server disagreed — resync rather than lie
  }

  const total = counts.new + counts.contacted + counts.closed;

  return (
    <div className="bookings">
      <div className="bk-head">
        <div className="bk-counts">
          <span className="bk-pill is-new">{counts.new} new</span>
          <span className="bk-pill">{counts.contacted} contacted</span>
          <span className="bk-pill is-closed">{counts.closed} closed</span>
        </div>
        <button className="icon-btn" data-tip="Refresh" aria-label="Refresh bookings" onClick={() => load()}>
          <IconRefresh />
        </button>
      </div>

      {total === 0 && !loading && (
        <div className="bk-empty">
          <span className="bk-empty-ico"><IconInbox /></span>
          <strong>No bookings yet</strong>
          <p className="muted">
            When a visitor sends the booking form on your published site,
            it lands here the moment they tap send.
          </p>
        </div>
      )}

      <div className="bk-list">
        {items.map((b) => (
          <article key={b.id} className={`bk-row st-${b.status}`}>
            <div className="bk-line">
              <strong className="bk-name">{b.name}</strong>
              <span className={`bk-status st-${b.status}`}>{b.status}</span>
              <time className="bk-time muted">{ago(b.created_at)}</time>
            </div>
            <div className="bk-line">
              <span className="bk-contact">{b.contact}</span>
              {b.service && <span className="bk-service">{b.service}</span>}
            </div>
            {b.message && <p className="bk-msg">{b.message}</p>}
            {NEXT[b.status] && (
              <button className="bk-action" onClick={() => advance(b)}>
                {NEXT[b.status]!.label}
              </button>
            )}
          </article>
        ))}
      </div>

      {cursor && (
        <button className="load-more" onClick={() => load(true, cursor)}>
          Show older bookings
        </button>
      )}
      {loading && items.length === 0 && total !== 0 && (
        <div className="history-spinner"><span className="spinner" /></div>
      )}
    </div>
  );
}
