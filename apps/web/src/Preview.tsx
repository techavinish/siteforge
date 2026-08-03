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

/** Builds the COMPLETE standalone website document — the same HTML that
 *  deploy_site will publish to Firebase Hosting. The preview shows the
 *  real thing in an isolated iframe, not an app-styled approximation. */
function buildSiteHtml(draft: Draft, activePath: string): string {
  const spec = draft.spec ?? {};
  const theme = spec.theme ?? {};
  const accent = theme.primary_color || "#333";
  const headFont = theme.fonts?.heading || "Georgia";
  const bodyFont = theme.fonts?.body || "system-ui";
  const siteName = spec.site_name ?? "Your Site";
  const pages = spec.pages ?? Object.keys(draft.pages ?? {}).map((p) => ({ path: p, title: p }));
  const body = marked.parse(draft.pages?.[activePath] ?? "", { async: false }) as string;

  const fontsQuery = [headFont, bodyFont]
    .map((f) => `family=${f.trim().replace(/ /g, "+")}:wght@400;600;700`)
    .join("&");

  const nav = pages
    .map(
      (p) =>
        `<a href="#" data-path="${p.path}" class="${p.path === activePath ? "on" : ""}">${p.title}</a>`,
    )
    .join("");

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${siteName}</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?${fontsQuery}&display=swap" rel="stylesheet">
<style>
  :root { --accent: ${accent}; }
  * { box-sizing: border-box; margin: 0; }
  body { font-family: "${bodyFont}", system-ui, sans-serif; color: #222; background: #fff; line-height: 1.7; }
  header {
    position: sticky; top: 0; z-index: 5; background: rgba(255,255,255,0.92);
    backdrop-filter: blur(8px); border-bottom: 1px solid #eee;
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px clamp(20px, 6vw, 56px);
  }
  .brand { font-family: "${headFont}", serif; font-weight: 700; font-size: 1.15rem; color: var(--accent); }
  nav { display: flex; gap: 22px; }
  nav a { color: #444; text-decoration: none; font-size: 0.85rem; padding-bottom: 2px; border-bottom: 2px solid transparent; }
  nav a:hover { color: var(--accent); }
  nav a.on { color: var(--accent); border-bottom-color: var(--accent); }
  main { max-width: 860px; margin: 0 auto; padding: 56px clamp(20px, 5vw, 40px) 80px; }
  h1, h2, h3 { font-family: "${headFont}", serif; line-height: 1.12; }
  h1 { font-size: clamp(2.2rem, 5.5vw, 3.4rem); letter-spacing: -0.015em; margin: 0.3em 0; }
  h1 + p strong { font-size: 1.15rem; color: #555; font-weight: 600; }
  h2 { font-size: 1.7rem; color: var(--accent); margin: 2.2em 0 0.5em; }
  h3 { font-size: 1.15rem; margin: 1.5em 0 0.4em; }
  p { margin: 0.8em 0; }
  main a {
    display: inline-block; margin: 6px 10px 6px 0; padding: 11px 24px;
    background: var(--accent); color: #fff; text-decoration: none;
    border-radius: 8px; font-weight: 600; font-size: 0.9rem;
    transition: filter .15s ease, transform .12s ease;
  }
  main a:hover { filter: brightness(1.1); transform: translateY(-1px); }
  ul, ol { padding-left: 24px; margin: 0.8em 0; }
  li { margin-bottom: 6px; }
  blockquote { border-left: 3px solid var(--accent); background: #fafafa; padding: 14px 20px; margin: 1.2em 0; border-radius: 0 8px 8px 0; }
  hr { border: none; border-top: 1px solid #eee; margin: 2.5em 0; }
  footer { border-top: 1px solid #eee; padding: 28px; text-align: center; font-size: 0.8rem; color: #888; }
</style>
</head>
<body>
<header><span class="brand">${siteName}</span><nav>${nav}</nav></header>
<main>${body}</main>
<footer>© ${new Date().getFullYear()} ${siteName} · Built with SiteForge</footer>
<script>
  document.querySelectorAll("nav a").forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    parent.postMessage({ sfNav: a.dataset.path }, "*");
  }));
</script>
</body>
</html>`;
}

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

  // the site's own nav (inside the iframe) drives page switching
  useEffect(() => {
    const onMsg = (e: MessageEvent) => {
      if (e.data?.sfNav && paths.includes(e.data.sfNav)) setActive(e.data.sfNav);
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [paths]);

  const srcDoc = useMemo(() => buildSiteHtml(draft, active), [draft, active]);

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
        srcDoc={srcDoc}
      />
    </aside>
  );
}
