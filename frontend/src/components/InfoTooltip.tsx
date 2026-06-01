"use client";

import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";

interface Props {
  label: string;
  text: string;
}

export default function InfoTooltip({ label, text }: Props) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  const handleEnter = () => {
    if (btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      setPos({
        top: r.top + window.scrollY - 8,
        left: r.left + window.scrollX + r.width / 2,
      });
    }
    setOpen(true);
  };

  return (
    <div style={{ position: "relative", display: "inline-flex" }}>
      <button
        ref={btnRef}
        onMouseEnter={handleEnter}
        onMouseLeave={() => setOpen(false)}
        onFocus={handleEnter}
        onBlur={() => setOpen(false)}
        style={{
          width: "15px", height: "15px",
          borderRadius: "50%",
          border: "1px solid var(--border-bright)",
          background: "transparent",
          color: "var(--text-muted)",
          fontSize: "9px", fontWeight: 700,
          cursor: "default",
          display: "flex", alignItems: "center", justifyContent: "center",
          lineHeight: 1, padding: 0, flexShrink: 0,
        }}
      >
        i
      </button>

      {mounted && open && createPortal(
        <div style={{
          position: "absolute",
          top: `${pos.top}px`,
          left: `${pos.left}px`,
          transform: "translate(-50%, -100%)",
          width: "270px",
          background: "#1a1a2e",
          border: "1px solid rgba(255,255,255,0.15)",
          borderRadius: "8px",
          padding: "10px 13px",
          fontSize: "11px",
          lineHeight: "1.65",
          color: "var(--text-secondary)",
          zIndex: 99999,
          boxShadow: "0 12px 32px rgba(0,0,0,0.7)",
          pointerEvents: "none",
        }}>
          <div style={{
            position: "absolute", bottom: "-5px", left: "50%",
            transform: "translateX(-50%) rotate(45deg)",
            width: "8px", height: "8px", background: "#1a1a2e",
            borderRight: "1px solid rgba(255,255,255,0.15)",
            borderBottom: "1px solid rgba(255,255,255,0.15)",
          }} />
          <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "11px", display: "block", marginBottom: "4px" }}>
            {label}
          </span>
          {text}
        </div>,
        document.body
      )}
    </div>
  );
}
