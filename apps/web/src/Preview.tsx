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
        <span className="preview-url">
          {(draft.spec?.site_name ?? "your-site").toLowerCase().replace(/\s+/g, "-")}.web.app
          {active === "/" ? "" : active}
        </span>
        {draft.score != null && <span className="score">★ {draft.score}/10</span>}
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
