"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Optionally log the error to an error reporting service
    console.error(error);
  }, [error]);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      minHeight: "50vh",
      gap: "16px"
    }}>
      <div style={{
        padding: "24px",
        background: "var(--bg-card)",
        border: "1px solid var(--border)",
        borderRadius: "12px",
        textAlign: "center",
        maxWidth: "400px"
      }}>
        <div style={{
          width: "48px",
          height: "48px",
          borderRadius: "50%",
          background: "var(--bearish-dim)",
          color: "var(--bearish)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          margin: "0 auto 16px",
          fontSize: "24px"
        }}>
          ⚠️
        </div>
        <h2 style={{ fontSize: "18px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "8px" }}>
          Něco se pokazilo
        </h2>
        <p style={{ fontSize: "14px", color: "var(--text-secondary)", marginBottom: "20px" }}>
          Při načítání aplikace došlo k chybě. Zkontrolujte, zda běží backend.
        </p>
        <button
          onClick={() => reset()}
          style={{
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            border: "1px solid var(--border-bright)",
            padding: "8px 16px",
            borderRadius: "6px",
            cursor: "pointer",
            fontSize: "13px",
            fontWeight: 500,
            transition: "all 0.2s"
          }}
        >
          Zkusit znovu
        </button>
      </div>
    </div>
  );
}
