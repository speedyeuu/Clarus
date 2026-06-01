"use client";

import { DailyScore } from "@/lib/types";
import InfoTooltip from "@/components/InfoTooltip";

interface Props {
  title: string;
  history: DailyScore[];
  dataKey: keyof DailyScore;
  tooltip?: string;
}

/**
 * Koláčový/gaugeový graf pro sentiment indikátory.
 *
 * Střed = 0 (pozice 12 hodin).
 * Kladné hodnoty jdou doprava (po směru hodinových ručiček) → zelená.
 * Záporné hodnoty jdou doleva (proti směru hodinových ručiček) → červená.
 * Rozsah je -3 až +3, přičemž ±3 zaplní přesně 180° (polovinu kruhu).
 */
export default function SentimentGaugeChart({ title, history, dataKey, tooltip }: Props) {
  const raw = history.length > 0
    ? (typeof history[history.length - 1][dataKey] === "number"
        ? (history[history.length - 1][dataKey] as number)
        : 0)
    : 0;

  const value = Math.max(-10, Math.min(10, raw));

  // ── Barvy ────────────────────────────────────────────────────────────────
  const color =
    value >= 1 ? "var(--bullish)"
    : value <= -1 ? "var(--bearish)"
    : "var(--neutral)";

  const dimColor =
    value >= 1 ? "rgba(34, 211, 160, 0.15)"
    : value <= -1 ? "rgba(244, 63, 94, 0.15)"
    : "rgba(107, 114, 128, 0.15)";

  const glowColor =
    value >= 1 ? "rgba(34, 211, 160, 0.35)"
    : value <= -1 ? "rgba(244, 63, 94, 0.35)"
    : "rgba(107, 114, 128, 0.2)";

  // ── Popis hodnoty ─────────────────────────────────────────────────────────
  const labelText =
    value >= 7 ? "Strong Bull"
    : value >= 3 ? "Bullish"
    : value >= 1 ? "Mild Bull"
    : value > -1 ? "Neutral"
    : value > -3 ? "Mild Bear"
    : value > -7 ? "Bearish"
    : "Strong Bear";

  // ── SVG geometrie ─────────────────────────────────────────────────────────
  const W = 220;
  const H = 210;
  const cx = 110;
  const cy = 108;
  const r = 64;          // poloměr středu tahu
  const sw = 18;         // šířka tahu (stroke-width)

  // Pomocná funkce: bod na kružnici v úhlu (radians, 0 = 3 hod, -π/2 = 12 hod)
  const pt = (angle: number, radius = r) => ({
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  });

  const startAngle = -Math.PI / 2; // 12 hodin = nula

  // Koncový úhel: value/10 * π posune o 0–180° od středu
  const endAngle = startAngle + (value / 10) * Math.PI;

  const s = pt(startAngle);
  const e = pt(endAngle);

  // large-arc-flag: nikdy nedosáhneme > 180°, takže vždy 0
  const largeArc = 0;
  // sweep-flag: 1 = po směru hodinových ručiček (pro kladné), 0 = opačně (záporné)
  const sweep = value >= 0 ? 1 : 0;

  const hasArc = Math.abs(value) > 0.1;
  const arcPath = hasArc
    ? `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 ${largeArc} ${sweep} ${e.x.toFixed(2)} ${e.y.toFixed(2)}`
    : null;

  // ── Dílky stupnice ────────────────────────────────────────────────────────
  const ticks = [
    { v: -10,  size: 10, w: 1.5 },
    { v: -5,   size: 6,  w: 1 },
    { v: 0,    size: 10, w: 1.5 },
    { v: 5,    size: 6,  w: 1 },
    { v: 10,   size: 10, w: 1.5 },
  ];

  // ── Zónové pozadí (polokruhy) ─────────────────────────────────────────────
  // Levá polovina (záporná zóna): od 12 hodin doleva ke spodku (CCW 180°)
  const negZoneBottom = pt(startAngle - Math.PI);
  const negZonePath = `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 0 0 ${negZoneBottom.x.toFixed(2)} ${negZoneBottom.y.toFixed(2)}`;
  // Pravá polovina (kladná zóna): od 12 hodin doprava ke spodku (CW 180°)
  const posZonePath = `M ${s.x.toFixed(2)} ${s.y.toFixed(2)} A ${r} ${r} 0 0 1 ${negZoneBottom.x.toFixed(2)} ${negZoneBottom.y.toFixed(2)}`;

  const uniqueId = `gauge-glow-${dataKey}`;

  return (
    <div
      className="card animate-slide-up"
      style={{ padding: "16px", flex: 1, minWidth: "250px" }}
    >
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px", alignItems: "flex-start" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div style={{
            fontSize: "12px", fontWeight: 600,
            color: "var(--text-primary)",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}>
            {title}
          </div>
          {tooltip && <InfoTooltip label={title} text={tooltip} />}
        </div>
        <div style={{
          fontSize: "13px", fontWeight: 600, fontFamily: "monospace",
          color, background: dimColor,
          padding: "3px 8px", borderRadius: "4px",
        }}>
          {value > 0 ? "+" : ""}{value.toFixed(0)}
        </div>
      </div>

      {/* SVG gauge */}
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: "auto", display: "block" }}
      >
        <defs>
          <filter id={uniqueId} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Zónové pozadí – záporná (levá) */}
        <path
          d={negZonePath}
          fill="none"
          stroke="rgba(244, 63, 94, 0.06)"
          strokeWidth={sw}
        />
        {/* Zónové pozadí – kladná (pravá) */}
        <path
          d={posZonePath}
          fill="none"
          stroke="rgba(34, 211, 160, 0.06)"
          strokeWidth={sw}
        />

        {/* Základní šedý kruh (celý objem) */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke="rgba(255,255,255,0.04)"
          strokeWidth={sw}
        />

        {/* Aktivní oblouk hodnoty */}
        {arcPath && (
          <>
            {/* Glow vrstva */}
            <path
              d={arcPath}
              fill="none"
              stroke={glowColor}
              strokeWidth={sw + 8}
              strokeLinecap="round"
            />
            {/* Hlavní oblouk */}
            <path
              d={arcPath}
              fill="none"
              stroke={color}
              strokeWidth={sw}
              strokeLinecap="round"
              filter={`url(#${uniqueId})`}
            />
          </>
        )}

        {/* Dílky stupnice */}
        {ticks.map(({ v, w }) => {
          const a = startAngle + (v / 10) * Math.PI;
          const inner = pt(a, r - sw / 2 - 2);
          const outer = pt(a, r + sw / 2 + 2);
          return (
            <line
              key={v}
              x1={inner.x} y1={inner.y}
              x2={outer.x} y2={outer.y}
              stroke="var(--border-bright)"
              strokeWidth={w}
              opacity={0.8}
            />
          );
        })}

        {/* Popisky dílků */}
        {/* Levý krajní: -10 */}
        {(() => {
          const a = startAngle + (-10 / 10) * Math.PI;
          const p = pt(a, r + sw / 2 + 14);
          return (
            <text x={p.x} y={p.y + 3} textAnchor="middle" fill="rgba(244,63,94,0.7)" fontSize="9" fontFamily="monospace">−10</text>
          );
        })()}
        {/* Střed: 0 */}
        {(() => {
          const a = startAngle;
          const p = pt(a, r + sw / 2 + 14);
          return (
            <text x={p.x} y={p.y - 2} textAnchor="middle" fill="var(--text-muted)" fontSize="9" fontFamily="monospace">0</text>
          );
        })()}
        {/* Pravý krajní: +10 */}
        {(() => {
          const a = startAngle + (10 / 10) * Math.PI;
          const p = pt(a, r + sw / 2 + 14);
          return (
            <text x={p.x} y={p.y + 3} textAnchor="middle" fill="rgba(34,211,160,0.7)" fontSize="9" fontFamily="monospace">+10</text>
          );
        })()}

        {/* Bod 0 na vrcholu (bílá tečka) */}
        <circle
          cx={s.x} cy={s.y} r={3}
          fill="var(--border-bright)"
        />

        {/* Středová hodnota */}
        <text
          x={cx} y={cy - 6}
          textAnchor="middle"
          fill={color}
          fontSize="26"
          fontWeight="700"
          fontFamily="'JetBrains Mono', monospace"
        >
          {value > 0 ? "+" : ""}{value.toFixed(0)}
        </text>
        <text
          x={cx} y={cy + 14}
          textAnchor="middle"
          fill="var(--text-muted)"
          fontSize="10"
          fontFamily="Inter, sans-serif"
          letterSpacing="0.03em"
        >
          {labelText}
        </text>

        {/* Levý/pravý label zóny */}
        <text x={20} y={cy + 28} textAnchor="middle" fill="rgba(244,63,94,0.35)" fontSize="8" fontFamily="monospace">BEAR</text>
        <text x={W - 20} y={cy + 28} textAnchor="middle" fill="rgba(34,211,160,0.35)" fontSize="8" fontFamily="monospace">BULL</text>
      </svg>
    </div>
  );
}
