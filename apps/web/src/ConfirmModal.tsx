import { useEffect, useRef } from "react";

export default function ConfirmModal({
  title,
  detail,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  title: string;
  detail: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      // Enter must NEVER be a global trigger for a destructive action
      if (e.key === "Tab" && boxRef.current) {
        const els = boxRef.current.querySelectorAll<HTMLElement>("button");
        if (!els.length) return;
        const first = els[0];
        const last = els[els.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener?.focus(); // hand focus back to whatever opened us
    };
  }, [onCancel]);

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="cm-title" aria-describedby="cm-detail" ref={boxRef} onClick={(e) => e.stopPropagation()}>
        <h3 id="cm-title">{title}</h3>
        <p className="muted" id="cm-detail">{detail}</p>
        <div className="modal-actions">
          <button onClick={onCancel} autoFocus>Cancel</button>
          <button className="danger" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
