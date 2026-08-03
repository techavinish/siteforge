import { useEffect, useState } from "react";
import { IconExpand, IconX } from "./icons";

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
  };
  pages?: Record<string, string>;
  score?: number;
  live_url?: string | null;
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
  const [active, setActive] = useState(paths[0] ?? "/");
  const [liveUrl, setLiveUrl] = useState<string | null>(draft.live_url ?? null);
  const [publishing, setPublishing] = useState(false);

  async function publishSite() {
    if (publishing) return;
    setPublishing(true);
    try {
      const r = await fetch(`/agent/publish/${threadId}`, { method: "POST" });
      if (!r.ok) throw new Error(`publish failed (${r.status})`);
      const { url } = await r.json();
      setLiveUrl(url);
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e));
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

      <iframe
        className="site-frame"
        title="Website preview"
        sandbox="allow-scripts"
        src={`/agent/site/${threadId}?path=${encodeURIComponent(active)}`}
      />
    </aside>
  );
}
