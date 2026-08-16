import { useEffect, useRef, useState } from "react";
import { IconChevronSmall } from "./icons";

export type ThinkBlock = { node: string; label: string; text: string };

// The structured nodes stream raw JSON as their "thinking" — a business
// owner must never see `{"brief": …}`. Only the page writer streams real,
// readable prose (the copy itself), so that's the only text we surface.
function readable(b: ThinkBlock): string {
  if (b.node !== "write_page") return "";
  // strip code fences / stray markdown scaffolding, keep the words
  return b.text.replace(/```[a-z]*/gi, "").trim();
}

// one friendly line per step — what's happening, in the owner's language
const STEP_BLURB: Record<string, string> = {
  understand: "Reading your business details",
  respond: "Composing a reply",
  plan: "Choosing colours, fonts, and page structure",
  illustrate: "Finding photographs",
  write_page: "Writing your page copy",
  review: "Checking the quality of every page",
};

/** Progress trace, ChatGPT/Claude-quiet: a single muted line whose label
 *  shimmers while working; expands to a clean step list (no raw JSON), with
 *  the writer's actual copy shown as it streams. */
export default function Thinking({
  blocks,
  streaming = false,
}: {
  blocks: ThinkBlock[];
  streaming?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [userToggled, setUserToggled] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  // auto-open only while actively streaming; auto-close when done, unless
  // the reader has taken manual control
  useEffect(() => {
    if (!userToggled) setOpen(streaming);
  }, [streaming, userToggled]);

  function onBodyScroll() {
    const el = bodyRef.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  }

  useEffect(() => {
    if (open && streaming && stick.current) {
      bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
    }
  }, [blocks, open, streaming]);

  if (!blocks.length) return null;
  const current = blocks[blocks.length - 1];
  // dedupe consecutive steps by node — one row per stage, not per token batch
  const steps = blocks.filter((b, i) => i === 0 || blocks[i - 1].node !== b.node);

  return (
    <div className={streaming ? "think live" : "think"}>
      <button
        className="think-head"
        onClick={() => {
          setUserToggled(true);
          setOpen((o) => !o);
        }}
        aria-expanded={open}
      >
        <span className={open ? "think-chev open" : "think-chev"}>
          <IconChevronSmall />
        </span>
        <span className={streaming ? "shimmer" : ""}>
          {streaming
            ? `${STEP_BLURB[current.node] ?? current.label}…`
            : `Built in ${steps.length} step${steps.length === 1 ? "" : "s"}`}
        </span>
      </button>
      {open && (
        <div className="think-body" ref={bodyRef} onScroll={onBodyScroll}>
          {steps.map((b, i) => {
            const last = i === steps.length - 1;
            const active = streaming && last;
            const copy = readable(b);
            return (
              <div key={`${b.node}-${i}`} className="think-step">
                <span className={active ? "step-dot on" : "step-dot"} />
                <div className="step-main">
                  <span className="step-name">{STEP_BLURB[b.node] ?? b.label}</span>
                  {copy && <pre className="step-copy">{copy}</pre>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
