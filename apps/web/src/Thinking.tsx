import { useEffect, useRef, useState } from "react";
import { IconChevronSmall } from "./icons";

export type ThinkBlock = { node: string; label: string; text: string };

/** Thinking trace, classic-quiet: a bare muted line whose label shimmers
 *  while streaming; opens behind a thin rule with reader-respecting
 *  scrolling (follows the stream only while you're at the bottom). */
export default function Thinking({
  blocks,
  streaming = false,
}: {
  blocks: ThinkBlock[];
  streaming?: boolean;
}) {
  const [open, setOpen] = useState(streaming);
  const [userToggled, setUserToggled] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

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

  return (
    <div className={streaming ? "think live" : "think"}>
      <button
        className="think-head"
        onClick={() => {
          setUserToggled(true);
          setOpen((o) => !o);
        }}
      >
        <span className={open ? "think-chev open" : "think-chev"}>
          <IconChevronSmall />
        </span>
        <span className={streaming ? "shimmer" : ""}>
          {streaming ? `${current.label}…` : "Thought process"}
        </span>
      </button>
      {open && (
        <div className="think-body" ref={bodyRef} onScroll={onBodyScroll}>
          {blocks.map((b, i) => (
            <div key={`${b.node}-${i}`} className="think-section">
              <span className="think-label">{b.label}</span>
              <pre>{b.text}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
