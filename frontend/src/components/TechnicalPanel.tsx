import type { TechnicalData } from "@/lib/api";

interface Props {
  data: TechnicalData | null;
}

function RsiGauge({ rsi }: { rsi: number }) {
  // RSI gauge: 0-100, zones: <30 oversold, >70 overbought
  const pct = Math.max(0, Math.min(100, rsi));
  const zone =
    rsi < 30 ? { color: "var(--bullish)", label: "Přeprodáno" } :
    rsi > 70 ? { color: "var(--bearish)", label: "Překoupeno" } :
               { color: "var(--text-secondary)", label: "Normální" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>RSI (14)</span>
        <span style={{ fontSize: "20px", fontWeight: 700, color: zone.color }}>{rsi.toFixed(1)}</span>
      </div>

      {/* Track */}
      <div style={{ position: "relative", height: "8px", borderRadius: "4px", background: "var(--bg-tertiary)", overflow: "hidden" }}>
        {/* Oversold zone (0-30) */}
        <div style={{ position: "absolute", left: 0, top: 0, width: "30%", height: "100%", background: "rgba(52,211,153,0.15)", borderRight: "1px solid rgba(52,211,153,0.3)" }} />
        {/* Overbought zone (70-100) */}
        <div style={{ position: "absolute", right: 0, top: 0, width: "30%", height: "100%", background: "rgba(239,68,68,0.15)", borderLeft: "1px solid rgba(239,68,68,0.3)" }} />
        {/* Cursor */}
        <div style={{
          position: "absolute",
          left: `calc(${pct}% - 5px)`,
          top: "-1px",
          width: "10px",
          height: "10px",
          borderRadius: "50%",
          background: zone.color,
          boxShadow: `0 0 6px ${zone.color}`,
          transition: "left 0.5s ease",
        }} />
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "var(--text-muted)" }}>
        <span style={{ color: "var(--bullish)" }}>0 Oversold</span>
        <span style={{ color: zone.color, fontWeight: 600 }}>{zone.label}</span>
        <span style={{ color: "var(--bearish)" }}>Overbought 100</span>
      </div>
    </div>
  );
}

function EmaRow({ label, pct, positive }: { label: string; pct: number; positive: boolean }) {
  const color = pct > 0 ? "var(--bullish)" : "var(--bearish)";
  const arrow = pct > 0 ? "▲" : "▼";
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <span style={{ fontSize: "12px", color }}>{arrow}</span>
        <span style={{ fontSize: "13px", fontWeight: 600, color }}>{Math.abs(pct).toFixed(3)}%</span>
      </div>
    </div>
  );
}

function AdxBadge({ adx }: { adx: number }) {
  const strength =
    adx >= 35 ? { label: "Silný trend", color: "var(--bullish)", bg: "rgba(52,211,153,0.12)" } :
    adx >= 20 ? { label: "Střední trend", color: "#f59e0b", bg: "rgba(245,158,11,0.12)" } :
                { label: "Ranging", color: "var(--text-secondary)", bg: "var(--bg-tertiary)" };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
      <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>ADX (14)</span>
      <div style={{
        padding: "2px 8px",
        borderRadius: "12px",
        background: strength.bg,
        border: `1px solid ${strength.color}40`,
        fontSize: "11px",
        fontWeight: 600,
        color: strength.color,
      }}>
        {adx.toFixed(1)} — {strength.label}
      </div>
    </div>
  );
}

function EntrySignalBanner({ signal }: { signal: TechnicalData["entry_signal"] }) {
  const colorMap: Record<string, { bg: string; border: string; text: string }> = {
    bullish:      { bg: "rgba(52,211,153,0.12)", border: "var(--bullish)", text: "var(--bullish)" },
    bearish:      { bg: "rgba(239,68,68,0.12)",  border: "var(--bearish)", text: "var(--bearish)" },
    mild_bullish: { bg: "rgba(52,211,153,0.07)", border: "#34d39966", text: "var(--bullish)" },
    mild_bearish: { bg: "rgba(239,68,68,0.07)",  border: "#ef444466", text: "var(--bearish)" },
    neutral:      { bg: "var(--bg-tertiary)",     border: "var(--border)", text: "var(--text-secondary)" },
  };
  const style = colorMap[signal.color] ?? colorMap.neutral;

  return (
    <div style={{
      padding: "12px 16px",
      borderRadius: "10px",
      background: style.bg,
      border: `1px solid ${style.border}`,
      display: "flex",
      flexDirection: "column",
      gap: "4px",
    }}>
      <span style={{ fontSize: "14px", fontWeight: 700, color: style.text }}>{signal.label}</span>
      <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{signal.description}</span>
    </div>
  );
}

export default function TechnicalPanel({ data }: Props) {
  if (!data) {
    return (
      <div className="card" style={{ padding: "20px" }}>
        <p style={{ color: "var(--text-muted)", fontSize: "13px", textAlign: "center" }}>
          Technická data nejsou k dispozici (zkontroluj price API klíč)
        </p>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "16px", flex: 1, minWidth: "280px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 700, color: "var(--text-primary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
          Technická analýza
        </h3>
        <span style={{ fontSize: "11px", color: "var(--text-muted)", background: "var(--bg-tertiary)", padding: "2px 8px", borderRadius: "6px" }}>
          D1 · EUR/USD
        </span>
      </div>

      {/* Entry Signal */}
      <EntrySignalBanner signal={data.entry_signal} />

      {/* RSI Gauge */}
      <RsiGauge rsi={data.rsi} />

      {/* EMA Distances */}
      <div>
        <span style={{ fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Vzdálenost od EMA
        </span>
        <div style={{ marginTop: "6px" }}>
          <EmaRow label="Cena vs EMA 20" pct={data.dist_from_ema20_pct} positive={data.dist_from_ema20_pct > 0} />
          <EmaRow label="Cena vs EMA 50" pct={data.dist_from_ema50_pct} positive={data.dist_from_ema50_pct > 0} />
          <EmaRow label="EMA 20 vs EMA 50" pct={data.ema_cross_pct} positive={data.ema20_above_ema50} />
        </div>
      </div>

      {/* ADX */}
      <AdxBadge adx={data.adx} />

      {/* Footer: Close price */}
      <div style={{ fontSize: "11px", color: "var(--text-muted)", textAlign: "right", borderTop: "1px solid var(--border)", paddingTop: "8px" }}>
        Poslední close: <strong style={{ color: "var(--text-secondary)" }}>{data.close.toFixed(5)}</strong>
      </div>
    </div>
  );
}
