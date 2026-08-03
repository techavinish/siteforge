import { useMemo, useState } from "react";
import { marked } from "marked";

export type Draft = {
  phase?: string;
  spec?: {
    site_name?: string;
    theme?: { mood?: string; primary_color?: string };
    pages?: { path: string; title: string }[];
  };
  pages?: Record<string, string>;
  score?: number;
};

export default function Preview({ draft }: { draft: Draft }) {
  const paths = Object.keys(draft.pages ?? {});
  const [active, setActive] = useState(paths[0] ?? "/");
  const accent = draft.spec?.theme?.primary_color || "#1b7a5f";

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
      </div>

      <nav className="preview-nav" style={{ borderColor: accent }}>
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
        style={{ ["--site-accent" as string]: accent }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </aside>
  );
}
