import { useEffect, useRef, useState } from "react";
import { IconExpand, IconX } from "./icons";

export type ThinkBlock = { node: string; label: string; text: string };

/** Collapsible thinking panel, claude-style: open and live-scrolling while
 *  streaming, collapses into a one-line summary when the answer starts —
 *  and expandable to a full overlay for reading the complete trace. */
export default function Thinking({
  blocks,
  streaming = false,
}: {
  blocks: ThinkBlock[];
  streaming?: boolean;
}) {
  const [open, setOpen] = useState(streaming);
  const [userToggled, setUserToggled] = useState(false);
  const [expanded, setExpanded] = useState(false);
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

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setExpanded(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  if (!blocks.length) return null;
  const current = blocks[blocks.length - 1];

  const sections = (
    <>
      {blocks.map((b, i) => (
        <div key={`${b.node}-${i}`} className="think-section">
          <span className="think-label">{b.label}</span>
          <pre>{b.text}</pre>
        </div>
      ))}
    </>
  );

  return (
    <div className={streaming ? "think live" : "think"}>
      <div className="think-bar">
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
        <button
          className="icon-btn think-expand"
          data-tip="Expand"
          onClick={() => setExpanded(true)}
        >
          <IconExpand />
        </button>
      </div>
      {open && (
        <div className="think-body" ref={bodyRef}>
          {sections}
        </div>
      )}

      {expanded && (
        <div className="modal-overlay" onClick={() => setExpanded(false)}>
          <div className="modal think-modal" onClick={(e) => e.stopPropagation()}>
            <div className="think-modal-head">
              <h3>Thought process</h3>
              <button className="icon-btn" onClick={() => setExpanded(false)}>
                <IconX />
              </button>
            </div>
            <div className="think-modal-body">{sections}</div>
          </div>
        </div>
      )}
    </div>
  );
}
