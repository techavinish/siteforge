import { useEffect, useState } from "react";
import { agentUrl, authFetch, idToken } from "./api";
import { IconExpand, IconGlobeSm, IconInbox, IconX } from "./icons";
import Bookings from "./Bookings";

export type Draft = {
  phase?: string;
  spec?: {
    site_name?: string;
    theme?: {
      mood?: string;
      primary_color?: string;
      fonts?: { heading?: string; body?: string };
    };
    pages?: { path: string; title: string }[];
    contact?: { mode?: string };
  };
  pages?: Record<string, string>;
  score?: number;
  live_url?: string | null;
  bookings?: { new: number; contacted: number; closed: number };
};

/** The canvas shows the agent-rendered website served by the backend
 *  (/agent/site/...) — the FE never assembles the site itself, so the
 *  preview and the future published site are the same document. */
export default function Preview({
  draft,
  threadId,
  wide,
  onToggleWide,
  onClose,
}: {
  draft: Draft;
  threadId: string;
  wide: boolean;
  onToggleWide: () => void;
  onClose: () => void;
}) {
  const paths = Object.keys(draft.pages ?? {});
  const [active, setActiveRaw] = useState(paths[0] ?? "/");
  const setActive = (p: string) => { setFrameLoading(true); setActiveRaw(p); };
  const [liveUrl, setLiveUrl] = useState<string | null>(draft.live_url ?? null);
  const [publishing, setPublishing] = useState(false);
  const [frameToken, setFrameToken] = useState("");
  const [frameLoading, setFrameLoading] = useState(true);
  const [pubError, setPubError] = useState("");
  const [tab, setTab] = useState<"site" | "bookings">("site");
  const [newCount, setNewCount] = useState(draft.bookings?.new ?? 0);

  // the Bookings tab exists once the client chose the tracker — or the
  // moment real bookings exist, whatever they later switched to
  const totalBookings =
    (draft.bookings?.new ?? 0) + (draft.bookings?.contacted ?? 0) + (draft.bookings?.closed ?? 0);
  const hasBookings = draft.spec?.contact?.mode === "tracker" || totalBookings > 0;

  // the iframe can't send headers — its src carries the ID token instead.
  // refreshed per navigation: firebase tokens expire hourly
  useEffect(() => {
    idToken().then(setFrameToken);
  }, [threadId, active]);

  // switching conversations = a different business's workspace
  useEffect(() => {
    setTab("site");
    setNewCount(draft.bookings?.new ?? 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, draft.bookings?.new]);

  // a regeneration can remove the page being viewed — never 404 the frame
  useEffect(() => {
    if (paths.length && !paths.includes(active)) setActive(paths[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  async function publishSite() {
    if (publishing) return;
    setPublishing(true);
    try {
      const r = await authFetch(`/agent/publish/${threadId}`, { method: "POST" });
      if (!r.ok) throw new Error(`publish failed (${r.status})`);
      const { url } = await r.json();
      setLiveUrl(url);
    } catch (e) {
      setPubError(e instanceof Error ? e.message : String(e));
      setTimeout(() => setPubError(""), 5000);
    } finally {
      setPublishing(false);
    }
  }

  // the site's own nav (inside the iframe) reports clicks back up
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.sfNav && paths.includes(e.data.sfNav)) setActive(e.data.sfNav);
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [paths]);

  if (!paths.length) return null;

  return (
    <aside className="preview">
      <div className="preview-chrome">
        <span className="dot" /><span className="dot" /><span className="dot" />
        {hasBookings && (
          <div className="seg" role="tablist" aria-label="Workspace panel">
            <button role="tab" aria-selected={tab === "site"}
              className={tab === "site" ? "on" : ""} onClick={() => setTab("site")}>
              <IconGlobeSm /> Website
            </button>
            <button role="tab" aria-selected={tab === "bookings"}
              className={tab === "bookings" ? "on" : ""} onClick={() => setTab("bookings")}>
              <IconInbox /> Bookings
              {newCount > 0 && <span className="seg-badge">{newCount}</span>}
            </button>
          </div>
        )}
        {liveUrl ? (
          <a className="preview-url live" href={liveUrl} target="_blank" rel="noreferrer">
            {liveUrl.replace("https://", "")}
            {active === "/" ? "" : active} ↗
          </a>
        ) : (
          <span className="preview-url">
            {(draft.spec?.site_name ?? "your-site").toLowerCase().replace(/\s+/g, "-")}.web.app
            {active === "/" ? "" : active}
          </span>
        )}
        {draft.score != null && <span className="score">★ {draft.score}/10</span>}
        <button
          className={publishing ? "publish busy" : "publish"}
          onClick={publishSite}
          data-tip={liveUrl ? "Publish latest version" : "Put this site live on the internet"}
        >
          {publishing ? "Publishing…" : liveUrl ? "Republish" : "Publish"}
        </button>
        <button className="icon-btn" data-tip={wide ? "Shrink" : "Expand"} onClick={onToggleWide}>
          <IconExpand />
        </button>
        <button className="icon-btn" data-tip="Close preview" onClick={onClose}>
          <IconX />
        </button>
      </div>

      {pubError && <div className="publish-toast" role="alert">{pubError}</div>}
      {tab === "bookings" ? (
        <Bookings threadId={threadId} onCounts={(c) => setNewCount(c.new)} />
      ) : (
        <div className="frame-wrap">
          {frameLoading && (
            <div className="frame-skeleton"><span className="spinner" /></div>
          )}
          {frameToken && (
            <iframe
              className="site-frame"
              title="Website preview"
              sandbox="allow-scripts"
              onLoad={() => setFrameLoading(false)}
              src={agentUrl(`/agent/site/${threadId}?path=${encodeURIComponent(active)}&token=${encodeURIComponent(frameToken)}`)}
            />
          )}
        </div>
      )}
    </aside>
  );
}
