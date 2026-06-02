"use client";

import { useRouter, useSearchParams } from "next/navigation";

// Aktivní páry — přidat nový pár = přidat sem + do backendu ACTIVE_PAIRS
const PAIRS = [
  { id: "EURUSD", label: "EUR/USD", flag: "🇪🇺" },
  { id: "GBPUSD", label: "GBP/USD", flag: "🇬🇧" },
  { id: "USDJPY", label: "USD/JPY", flag: "🇯🇵" },
  { id: "AUDUSD", label: "AUD/USD", flag: "🇦🇺" },
];

interface Props {
  activePair: string;
}

export default function PairSelector({ activePair }: Props) {
  const router = useRouter();

  const handleSelect = (pairId: string) => {
    const params = new URLSearchParams({ pair: pairId });
    router.push(`/?${params.toString()}`);
  };

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: "6px",
      background: "var(--bg-elevated)",
      border: "1px solid var(--border)",
      borderRadius: "10px",
      padding: "4px",
    }}>
      {PAIRS.map((p) => {
        const isActive = activePair === p.id;
        return (
          <button
            key={p.id}
            onClick={() => handleSelect(p.id)}
            title={p.label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "5px 12px",
              borderRadius: "7px",
              border: "none",
              cursor: "pointer",
              fontSize: "13px",
              fontWeight: isActive ? 700 : 500,
              fontFamily: "var(--font-mono, monospace)",
              letterSpacing: "0.03em",
              transition: "all 0.15s ease",
              background: isActive
                ? "linear-gradient(135deg, rgba(52,211,153,0.2) 0%, rgba(16,185,129,0.1) 100%)"
                : "transparent",
              color: isActive ? "var(--bullish)" : "var(--text-secondary)",
              boxShadow: isActive ? "inset 0 0 0 1px rgba(52,211,153,0.35)" : "none",
            }}
          >
            <span style={{ fontSize: "15px" }}>{p.flag}</span>
            <span>{p.label}</span>
          </button>
        );
      })}
    </div>
  );
}
