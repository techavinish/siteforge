import { useEffect, useRef, useState } from "react";

export type ThinkBlock = { node: string; label: string; text: string };

/** Collapsible thinking panel, claude-style: open and live-scrolling while
 *  streaming, auto-collapses into a one-line summary when the answer starts. */
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

  // follow the streaming state unless the user took manual control
  useEffect(() => {
    if (!userToggled) setOpen(streaming);
  }, [streaming, userToggled]);

  // keep the live feed scrolled to the newest thought
  useEffect(() => {
    if (open && streaming) {
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
        <span className="think-dot" />
        <span>{streaming ? current.label : "Thought process"}</span>
        <span className="think-chev">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="think-body" ref={bodyRef}>
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
