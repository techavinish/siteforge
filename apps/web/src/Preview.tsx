import { useEffect, useMemo, useState } from "react";
import { marked } from "marked";
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

export default function Preview({
  draft,
  wide,
  onToggleWide,
  onClose,
}: {
  draft: Draft;
  wide: boolean;
  onToggleWide: () => void;
  onClose: () => void;
}) {
  const paths = Object.keys(draft.pages ?? {});
  const [active, setActive] = useState(paths[0] ?? "/");
  const theme = draft.spec?.theme;
  const accent = theme?.primary_color || "#1b7a5f";
  const headFont = theme?.fonts?.heading;
  const bodyFont = theme?.fonts?.body;

  // the generated site gets ITS OWN fonts, loaded on demand — the brand
  // identity belongs to the agent's spec, not to the SiteForge app shell
  useEffect(() => {
    if (!headFont && !bodyFont) return;
    const fams = [headFont, bodyFont]
      .filter(Boolean)
      .map((f) => `family=${f!.trim().replace(/ /g, "+")}:wght@400;600;700`)
      .join("&");
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = `https://fonts.googleapis.com/css2?${fams}&display=swap`;
    document.head.appendChild(link);
    return () => link.remove();
  }, [headFont, bodyFont]);

  const html = useMemo(() => {
    const md = draft.pages?.[active] ?? "";
    return marked.parse(md, { async: false }) as string;
  }, [draft.pages, active]);

  const titleFor = (p: string) =>
    draft.spec?.pages?.find((x) => x.path === p)?.title ?? (p === "/" ? "Home" : p.slice(1));

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

      <nav className="preview-nav">
        {paths.map((p) => (
          <button
            key={p}
            className={p === active ? "tab active" : "tab"}
            style={p === active ? { background: accent, borderColor: accent } : {}}
            onClick={() => setActive(p)}
          >
            {titleFor(p)}
          </button>
        ))}
      </nav>

      <div
        className="preview-page"
        style={{
          ["--site-accent" as string]: accent,
          ["--site-font-head" as string]: headFont ? `"${headFont}", serif` : "inherit",
          fontFamily: bodyFont ? `"${bodyFont}", system-ui, sans-serif` : undefined,
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </aside>
  );
}
